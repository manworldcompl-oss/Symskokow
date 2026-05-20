# Biblioteki standardowe
import os
import glob
import re
import threading
import traceback
import unicodedata
from math import inf
from pathlib import Path
from datetime import date

# Tkinter
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Numeryczne i dane
import numpy as np
import pandas as pd
from pandas import ExcelFile
from pandas.api.types import is_numeric_dtype

# Lokalne moduły
import ski_jump_simulator_random_v6 as sim
from flags_cache import FLAG_CACHE
from ski_jump_simulator_random_v6 import _fis_points_for_place
from aktualizuj_klasyfikacje import aktualizuj_najnowszy_wynik

# --- FLAG CACHE HELPERS (auto-injected) ---
def _flag_cached(code: str | None):
    try:
        return FLAG_CACHE.get(code) or FLAG_CACHE.blank()
    except Exception:
        return FLAG_CACHE.blank()

def _tv_clear_img_refs(tv):
    old = getattr(tv, "img_refs", None)
    if isinstance(old, list):
        try:
            old.clear()
        except Exception:
            pass
        try:
            delattr(tv, "img_refs")
        except Exception:
            pass

def _tv_push_img(tv, img):
    if not hasattr(tv, "img_refs"):
        tv.img_refs = []
    tv.img_refs.append(img)
# --- END HELPERS ---

def _to_bool(x):
    if x is None:
        return False
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return x != 0
    if isinstance(x, float):
        if np.isnan(x) or np.isinf(x):
            return False
        return x != 0.0
    if isinstance(x, str):
        return x.strip().lower() in ("1", "true", "yes", "y", "t", "prawda")  # <-- dodane "prawda"
    return False

# ===== KLASYFIKACJE v4 — CSV-first loader (drop‑in replacement) =====
# Wklej TĘ klasę zamiast poprzedniej "KlasyfikacjeTab" w pliku ski_jump_gui_full_embedded.py.
# Domyślnie czyta CSV-y z folderu ./Klasyfikacje o nazwach np.:
#   AC-M__players.csv, AC-M__nations.csv, ..., WC-W__players.csv, ...
# Jeśli CSV-ów nie ma, możesz nadal kliknąć "Wczytaj z Excela" (kompatybilność wsteczna).
class KlasyfikacjeTab(ttk.Frame):
    BASE_PREFIXES = ["WC","COC","FC","GP","SCOC","JC","MC","PC","QC","TC","AC","BC","DC"]
    DEFAULT_ORDER = [f"{p}-M" for p in BASE_PREFIXES] + [f"{p}-W" for p in BASE_PREFIXES]

    def __init__(self, parent, default_excel="Klasyfikacje2 S45 — kopia.xlsx", flag_dir="./flags", default_dir="./S45/Klasyfikacje S45"):
        super().__init__(parent)
        self.excel_var = tk.StringVar(value=default_excel)
        self.dir_var = tk.StringVar(value=default_dir)
        self.nb_sheets = ttk.Notebook(self)
        self.flag_dir = flag_dir
        self._flag_cache = {}
        self._blank_flag = None
        self.sheet_data = {}

        self._build_header()
        self.nb_sheets.pack(fill=tk.BOTH, expand=True)

        # Auto: spróbuj CSV-y, a jeśli brak — nie wieszaj się.
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

        # CSV dir
        ttk.Label(bar, text="Folder CSV:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.dir_var, width=38).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="…", command=self._browse_dir).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(bar, text="Wczytaj CSV", command=self.load_csv_dir).pack(side=tk.LEFT, padx=(0,12))

        # Excel (legacy)
        ttk.Label(bar, text="Excel (legacy):").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.excel_var, width=36).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="…", command=self._browse_excel).pack(side=tk.LEFT)
        ttk.Button(bar, text="Wczytaj z Excela", command=self.load_excel).pack(side=tk.LEFT, padx=6)

        self.info_lbl = ttk.Label(bar, text="", foreground="#666")
        self.info_lbl.pack(side=tk.LEFT, padx=10)

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
                img = FLAG_CACHE.blank()
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
    def _make_table_with_flags(self, parent, df, name_col, code_col, lp_heading="Lp.", height=25):
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
            width = max(60, min(220, int(df[c].astype(str).map(len).max() * 7.0) if len(df) else 100))
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
            delta = -1 * (e.delta // 120)
            tvL.yview_scroll(delta, "units")
            tvR.yview_scroll(delta, "units")
            return "break"
        for w in (tvL, tvR):
            w.bind("<MouseWheel>", _wheel)

        syncing = False
        def _sync_from_R(_):
            nonlocal syncing
            if syncing: return
            sel = tvR.selection()
            if not sel: return
            idx = tvR.index(sel[0])
            idsL = tvL.get_children()
            if idx >= len(idsL): return
            syncing = True
            try:
                if tvL.selection() != (idsL[idx],):
                    tvL.selection_set(idsL[idx]); tvL.see(idsL[idx])
            finally:
                syncing = False

        def _sync_from_L(_):
            nonlocal syncing
            if syncing: return
            sel = tvL.selection()
            if not sel: return
            idx = tvL.index(sel[0])
            idsR = tvR.get_children()
            if idx >= len(idsR): return
            syncing = True
            try:
                if tvR.selection() != (idsR[idx],):
                    tvR.selection_set(idsR[idx]); tvR.see(idsR[idx])
            finally:
                syncing = False

        tvR.bind("<<TreeviewSelect>>", _sync_from_R)
        tvL.bind("<<TreeviewSelect>>", _sync_from_L)

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

        tvR.img_refs = []
        lp_col = "LP." if "LP." in df.columns else ("Lp." if "Lp." in df.columns else None)
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
        df.columns = KlasyfikacjeTab._clean_headers(df.columns)
        # zobacz, czy nagłówki są już docelowe
        up = [c.upper() for c in df.columns]
        # mapowanie znanych wariantów
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
        # uzupełnij brakujące LP. jeśli trzeba
        if "LP." not in df.columns:
            df.insert(0, "LP.", range(1, len(df)+1))
        # trym do 4 kolumn (LP., JUMPER, NAT, PTS) + odetnij puste
        keep = [c for c in ["LP.", "JUMPER", "NAT", "PTS"] if c in df.columns]
        out = df[keep].copy().dropna(how="all")
        # normalizacje
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
        df.columns = KlasyfikacjeTab._clean_headers(df.columns)
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
        # bazowy podzbiór: z T/I jeśli dostępne
        base_n = ["LP.", "NATION", "NAT", "PTS"]
        with_ti = ["LP.", "NATION", "NAT", "T", "I", "PTS"]
        if set(with_ti).issubset(set(df.columns)):
            keep = with_ti
        else:
            keep = [c for c in base_n if c in df.columns]
        out = df[keep].copy().dropna(how="all")
        # normalizacje
        if "PTS" in out.columns:
            out["PTS"] = pd.to_numeric(out["PTS"], errors="coerce").fillna(0.0)
        if "NAT" in out.columns:
            out["NAT"] = out["NAT"].fillna("").astype(str).str.upper()
        # LP. jeśli brak
        if "LP." not in out.columns:
            out.insert(0, "LP.", range(1, len(out)+1))
        return out

    def _clear_notebook(self):
        for child in self.nb_sheets.winfo_children():
            child.destroy()
        for tab_id in self.nb_sheets.tabs():
            self.nb_sheets.forget(tab_id)

    # ---------- public: for quotas tab ----------
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
    def _pick_classif_file(self, root: str, tag: str, kind: str) -> str | None:
        """
        Szuka <tag>__{kind}.csv z opcjonalnym prefiksem:
        - {tag}__{kind}.csv
        - S45_{tag}__{kind}.csv
        - dowolne *_<tag>__{kind}.csv
        Zwraca pełną ścieżkę (najświeższą), albo None.
        """
        candidates = []

        # bez prefiksu
        base = os.path.join(root, f"{tag}__{kind}.csv")
        if os.path.isfile(base):
            candidates.append(base)

        # typowy prefiks sezonu
        pref = os.path.join(root, f"S45_{tag}__{kind}.csv")
        if os.path.isfile(pref):
            candidates.append(pref)

        # dowolny prefiks
        candidates += glob.glob(os.path.join(root, f"*_{tag}__{kind}.csv"))

        if not candidates:
            return None

        # wybierz najnowszy mtime
        candidates = list(set(candidates))  # bez duplikatów
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidates[0]

    def load_csv_dir(self):
        root = self.dir_var.get().strip() or "./S44/Klasyfikacje S44"
        tags = [t for t in self.DEFAULT_ORDER]
        missing = 0
        self.sheet_data = {}
        self._clear_notebook()
        
        for tag in tags:
            tab = ttk.Frame(self.nb_sheets)
            self.nb_sheets.add(tab, text=tag)

            players_path = self._pick_classif_file(root, tag, "players")
            nations_path = self._pick_classif_file(root, tag, "nations")

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

        self.info_lbl.config(text=f"Wczytano CSV z: {os.path.abspath(root)}")

    # Legacy Excel loader — zachowany dla kompatybilności
    def load_excel(self):
        path = self.excel_var.get()
        try:
            xls = ExcelFile(path, engine="openpyxl")
        except Exception as e:
            self.info_lbl.config(text=f"Nie mogę wczytać: {e}")
            return

        sheets = [s for s in self.DEFAULT_ORDER if s in xls.sheet_names]
        self._clear_notebook()
        self.info_lbl.config(text=f"Arkuszy: {len(sheets)}")

        # Proste heurystyki wykrojenia bloków jak w poprzedniej wersji:
        def _simple_blocks(df_raw):
            # Zakładamy, że CSV zamienił się w „czysty” arkusz: poszukaj kolumn
            df = df_raw.copy()
            df.columns = [str(c).strip().upper() for c in df.columns]
            # Gracz
            p_cols = [c for c in ("LP.","LP", "JUMPER","NAT","PTS") if c in df.columns]
            players = df[p_cols].copy() if {"JUMPER","NAT"}.issubset(set(p_cols)) else None
            if isinstance(players, pd.DataFrame) and "LP." not in players.columns and "LP" in players.columns:
                players.rename(columns={"LP":"LP."}, inplace=True)
            # Kraj
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
# ===== KLASYFIKACJE v4 — koniec =====

class _FlagCache:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self._cache = {}
        self.sheet_data = {}
    def get(self, code: str):
        code = (code or "").strip().lower()
        p = self.folder / f"{code}.png"
        if not p.exists(): return None
        key = str(p.resolve())
        if key not in self._cache:
            self._cache[key] = tk.PhotoImage(file=str(p))
        return self._cache[key]

# --- Fallback dla miejsc ex aequo, jeśli nie ma w silniku ---
if not hasattr(sim, "_apply_tied_places"):
    def _apply_tied_places(df, points_col: str, place_col: str = "Miejsce", ascending: bool = False):
        if df is None or len(df) == 0 or points_col not in df.columns:
            return df
        out = df.copy()
        if place_col in out.columns:
            out = out.drop(columns=[place_col])
        out.insert(0, place_col, out[points_col].rank(method="min", ascending=ascending).astype(int))
        return out
else:
    _apply_tied_places = sim._apply_tied_places  # użyj z silnika, jeśli istnieje

APP_TITLE = "Ski Jump Simulator – IND GUI (Full KO64 + Classic + KO50)"
FLAGS_DIR = "./flags"
BYE_NAME_RE = re.compile(r'^\s*(?:\[\s*BYE\s*\]|BYE(?:\s+\d+)?)\s*$', re.I)



# === HELPERY v3 (meta dla Upadków) ===
# === RESOLVER ŚCIEŻEK (szuka w CWD i przy pliku .py) ===
# === UNIVERSAL FILE LOCATOR (obsługuje S45/ i S44/) ===
def _find_nearby_file(basename, alt_patterns=()):
    """
    Szuka pliku wg nazwy/wzorca w:
      - cwd
      - folderze tego pliku
      - podfolderach 'S45' i 'S44' (dla obu powyższych korzeni)
    Wspiera zarówno dokładne nazwy jak i globy (np. '*Sztab* S45*.csv').
    Zwraca ścieżkę jako str albo None.
    """

    def _roots():
        roots = [Path.cwd()]
        try:
            roots.append(Path(__file__).resolve().parent)
        except Exception:
            pass
        # dorzuć warianty S45/ i S44/
        ext = []
        for r in roots:
            ext.append(r / "S45")
            ext.append(r / "S44")
        return roots + ext

    roots = [p for p in _roots() if p.exists()]

    # 0) Jeśli basename już jest ścieżką istniejącą — zwróć
    try:
        p_in = Path(basename)
        if p_in.exists():
            return str(p_in)
    except Exception:
        pass

    patterns = [str(basename)] + [str(p) for p in (alt_patterns or [])]

    # 1) Dokładne trafienie po nazwie (case-insensitive) w każdym korzeniu
    low_name = str(basename).lower()
    for r in roots:
        candidate = r / basename
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        # przeglądnij wszystkie csv w tym katalogu
        for f in r.glob("*.csv"):
            try:
                if f.name.lower() == low_name:
                    return str(f)
            except Exception:
                continue

    # 2) Glob w każdym korzeniu (bez rekursji – szybko)
    for r in roots:
        for pat in patterns:
            for f in r.glob(pat):
                try:
                    if f.is_file():
                        return str(f)
                except Exception:
                    continue

    # 3) Ostatnia deska ratunku: rekursywnie w S45/ i S44/ (jak ktoś jeszcze niżej schował)
    for r in roots:
        if r.name.upper() in {"S45", "S44"} and r.is_dir():
            for pat in patterns:
                try:
                    for f in r.rglob(pat):
                        if f.is_file():
                            return str(f)
                except Exception:
                    continue

    return None

def _read_tab_any(path):
    last_err = None
    # Najpierw CSV ze średnikiem, potem przecinek; z fallbackiem enkodowania
    for sep in (";", ","):
        for enc in ("utf-8", "utf-8-sig", "cp1250", "latin1"):
            try:
                # DODANO: na_values=['-', ''] - to zamieni myślniki na NaN (puste pola)
                df = pd.read_csv(path, sep=sep, engine="python", encoding=enc, na_values=['-', ''])
                # DODANO: fillna(0) - zamieniamy puste pola na zero, żeby matematyka działała
                df = df.fillna(0)
                print(f"DEBUG READ OK: {path} sep='{sep}' enc='{enc}' shape={getattr(df,'shape',None)}")
                return df
            except Exception as e:
                last_err = e
                continue
    try:
        df = pd.read_excel(path)
        return df.fillna(0)
    except Exception as e:
        last_err = e
        print("DEBUG READ FAIL:", path, "->", last_err)
        return None
    
def _col(df, aliases, prefix_ok=False):
    if df is None or df.empty:
        return None
    low = {str(c).strip().lower(): c for c in df.columns}
    for a in aliases:
        a=a.lower()
        if a in low: return low[a]
    if prefix_ok:
        for a in aliases:
            a=a.lower()
            for k,orig in low.items():
                if k.startswith(a): return orig
    return None

def _load_infra_centrum_med(path="Infrastruktura S45.csv"):
    path = _find_nearby_file(path, alt_patterns=["*Infrastruktura* S45*.csv", "*Infrastruktura*.csv"])
    df = _read_tab_any(path) if path else None
    if df is None:
        print("DEBUG INFRA: brak pliku", path); return {}
    nat_col = _col(df, ["KRAJ","NAT","Kod","Country"])
    name_col= _col(df, ["REPREZENTACJA","Reprezentacja","Country Name"])
    med_col = _col(df, ["Centrum Medyczne","Centrum med.","Centrum med","centrum medyczne"], prefix_ok=True)
    if not med_col or (not nat_col and not name_col):
        print("DEBUG INFRA: brak kolumn", nat_col, name_col, med_col); return {}
    out={}
    if nat_col:
        for _,r in df.iterrows():
            k=str(r.get(nat_col,"")).strip().upper()
            if k: out[k]=r.get(med_col,"")
    if name_col:
        for _,r in df.iterrows():
            k=str(r.get(name_col,"")).strip().upper()
            if k and k not in out: out[k]=r.get(med_col,"")
    print("DEBUG INFRA: kraje=", len(out))
    return out

def _load_best_staff_um(staff_path, want_sex: str, role_is_doctor_only=True):
    """
    NAT -> max(UM) dla Sex (M/W).
    Najpierw Code=='L' (lekarz). Jeśli w kraju brak L, fallback: najlepszy UM dowolnej roli.
    """
    staff_path = _find_nearby_file(
        staff_path,
        alt_patterns=[
            "*Sztab* S45*.csv",
            "*Sztab*_*S45*.csv",
            "*Sztab* M*.csv" if " M " in staff_path or staff_path.endswith(" M S45.csv") else "*Sztab* W*.csv",
        ]
    )
    df = _read_tab_any(staff_path) if staff_path else None
    if df is None:
        print("DEBUG STAFF: brak", staff_path); return {}
    nat_col  = _col(df, ["NAT","Kraj","Reprezentacja","Country"])
    code_col = _col(df, ["Code","Kod","Funkcja","Rola"])
    sex_col  = _col(df, ["Sex","Płeć","Pleć","Plec"])
    um_col   = _col(df, ["UM","Um","um"])
    if not (nat_col and code_col and sex_col and um_col):
        print("DEBUG STAFF: brak kolumn", nat_col, code_col, sex_col, um_col); return {}
    
    tmp = df.copy()
    tmp[sex_col] = tmp[sex_col].astype(str).str.upper().str[:1].map(lambda x: "W" if x=="F" else x)
    tmp[nat_col] = tmp[nat_col].astype(str).str.upper().str.strip()
    tmp["_UM_"]  = pd.to_numeric(tmp[um_col], errors="coerce")
    sub = tmp[tmp[sex_col] == str(want_sex).upper()[:1]]
    sub_doc = sub[sub[code_col].astype(str).str.strip().str.upper().eq("L")] if role_is_doctor_only else sub
    def _best(df_nat):
        if df_nat.empty: return {}
        best = (df_nat.dropna(subset=["_UM_"]).sort_values("_UM_", ascending=False)
                .drop_duplicates(subset=[nat_col]))
        return dict(zip(best[nat_col], best["_UM_"]))
    out = _best(sub_doc)
    if role_is_doctor_only:
        missing = {k for k in sub[nat_col].unique() if k not in out}
        if missing:
            any_map = _best(sub[sub[nat_col].isin(missing)])
            out.update({k:any_map.get(k,"") for k in missing if k in any_map})
    print(f"DEBUG STAFF: {staff_path} ({want_sex}) ->", len(out), "krajów")
    return out

def _enrich_falls_with_meta(falls_df, roster_df):
    
    if not isinstance(falls_df, pd.DataFrame) or falls_df.empty:
        print("DEBUG FALLS: pusto"); return falls_df
    kraj_falls = next((c for c in ("Kraj","NAT","Reprezentacja","Drużyna","Druzyna") if c in falls_df.columns), None)
    name_f     = "Zawodnik" if "Zawodnik" in falls_df.columns else None
    name_r = next((c for c in ("Zawodnik","Name","Nazwisko") if c in roster_df.columns), None)
    sex_r  = next((c for c in ("Płeć","Pleć","Plec","Sex") if c in roster_df.columns), None)
    if name_r and sex_r and name_f:
        tmp = roster_df[[name_r, sex_r]].copy()
        tmp[sex_r] = tmp[sex_r].astype(str).str.upper().str[:1].map(lambda x: "W" if x=="F" else x)
        falls_df["Sex"] = falls_df[name_f].map(dict(zip(tmp[name_r], tmp[sex_r]))).fillna("")
    else:
        falls_df["Sex"] = ""
    docs_M = _load_best_staff_um("Sztab M S45.csv", "M", role_is_doctor_only=True)
    docs_W = _load_best_staff_um("Sztab W S45.csv", "W", role_is_doctor_only=True)
    def _um_for(nat, sx):
        nat = str(nat).strip().upper(); sx = str(sx).strip().upper()
        if not nat: return ""
        if sx=="W": return docs_W.get(nat, "")
        if sx=="M": return docs_M.get(nat, "")
        return docs_M.get(nat, "") or docs_W.get(nat, "")
    falls_df["Lekarz"] = falls_df.apply(lambda r: _um_for(r.get(kraj_falls,""), r.get("Sex","")) if kraj_falls else "", axis=1)
    infra = _load_infra_centrum_med("Infrastruktura S45.csv")
    if kraj_falls:
        falls_df["Infrastruktura"] = falls_df[kraj_falls].astype(str).str.upper().map(infra).fillna("")
    else:
        falls_df["Infrastruktura"] = ""
    try:
        print("DEBUG FALLS sample:\n",
              falls_df[[x for x in ("Zawodnik", kraj_falls or "Kraj", "Sex", "Lekarz", "Infrastruktura") if x in falls_df.columns]].head(5))
    except Exception: pass
    # kolejność
    order=[]
    for c in ("Runda","Zawodnik", kraj_falls if kraj_falls else "Kraj"):
        if c in falls_df.columns: order.append(c)
    for c in ("Sex","Lekarz","Infrastruktura"):
        if c in falls_df.columns: order.append(c)
    rest=[c for c in falls_df.columns if c not in order]
    return falls_df[order+rest]
# === KONIEC helperów ===

def _normalize_points(df: pd.DataFrame, col: str = "Punkty", decimals: int = 1) -> pd.DataFrame:
    """Zaokrągla i ‘usztywnia’ punkty: key = rint(punkty * 10^decimals) / 10^decimals.
       Dzięki temu 299.799999… -> 299.8 i ex aequo działa deterministycznie."""
    if not isinstance(df, pd.DataFrame) or df.empty or col not in df.columns:
        return df
    s = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    scale = 10 ** int(decimals)
    key = np.rint(s.to_numpy() * scale).astype(np.int64)
    df = df.copy()
    df[col] = (key.astype(np.float64) / scale).round(decimals)
    return df

def _norm_name_key(x: str) -> str:
    if x is None:
        return ""
    s = str(x).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def _comp_base_tag(val: str) -> str:
    s = str(val or "").strip().upper()
    # "WC-M" → "WC", "COC-W" → "COC", "FC" zostaje "FC"
    return re.sub(r"-(?:M|W)$", "", s)

# ======== KO64 full tournament helper (embedded) ========
def _pair_indices(n: int):
    """Parowanie po sąsiedzku: (0,1), (2,3), ... – zgodnie ze stałą drabinką.
    Następne rundy zachowują kolejność bracketu.
    """
    return [(i, i+1) for i in range(0, n, 2)]

def _prep_field(df_rank: pd.DataFrame, top_n: int = 64) -> pd.DataFrame:
    r = df_rank.copy()
    if "Zawodnik" in r.columns:
        r["__key"] = r["Zawodnik"].map(_norm_name_key)
        r = r.drop_duplicates(subset=["__key"], keep="first").drop(columns=["__key"])
    if "Punkty" in r.columns:
        r = r.sort_values("Punkty", ascending=False, kind="stable").reset_index(drop=True)
    r["Seed"] = np.arange(1, len(r)+1)
    return r.head(top_n).reset_index(drop=True)

def _round_label(r: int) -> str:
    labels = {1:"R1 (64)", 2:"R2 (32)", 3:"R3 (16)", 4:"QF (8)", 5:"SF (4)", 6:"F (2)"}
    return labels.get(r, f"R{r}")

# === BYE & bracket helpers (GUI) ===
def _bracket_seed_order(n: int = 64):
    order = [1]
    while len(order) < n:
        m = len(order) * 2
        order = [y for x in order for y in (x, m + 1 - x)]
    return order  # 1-based

def _fill_byes_to_64(field: pd.DataFrame, size: int = 64) -> pd.DataFrame:
    f = field.copy()
    f["Seed"] = np.arange(1, len(f) + 1)
    if len(f) >= size:
        f["IsBYE"] = False
        return f.head(size).reset_index(drop=True)
    byes = []
    for seed in range(len(f) + 1, size + 1):
        byes.append({"Seed": seed, "Zawodnik": f"BYE {seed}",
                     "UM": 0.0, "Forma": 0.0, "Kraj": "", "IsBYE": True})
    f["IsBYE"] = False
    return pd.concat([f, pd.DataFrame(byes)], ignore_index=True).reset_index(drop=True)


def simulate_full_ko64_tournament(
    roster: pd.DataFrame,
    K: int,
    HS: int,
    meter_value: float,
    wind_ms_mean: float,
    wind_ms_sd: float,
    gate_base: int,
    gate_points_per_step: float,
    p_gate_change: float,
    max_gate_delta: int,
    rng: np.random.Generator | None,
    randomness: float,
    elite_regress: float,
    wind_phi: float,
    wind_takeoff_gain: float,
    wind_flight_gain: float,
    judges_rho: float,
):
    if meter_value is None:
        meter_value = sim.compute_meter_value(K)
    rng = rng or np.random.default_rng()

    # --- Kwalifikacje ---
    kwal_df = sim.simulate_round(
        roster=roster, K=K, HS=HS, meter_value=meter_value,
        wind_ms_mean=wind_ms_mean, wind_ms_sd=wind_ms_sd,
        gate_base=gate_base, gate_points_per_step=gate_points_per_step,
        p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
        rng=rng, randomness=randomness, elite_regress=elite_regress,
        wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
        wind_flight_gain=wind_flight_gain, judges_rho=judges_rho,
        sort_output=True,
    )
    kval_rank = kwal_df.copy()
    if "Punkty rundy" in kval_rank.columns:
        kval_rank.rename(columns={"Punkty rundy":"Punkty"}, inplace=True)
    if "Miejsce w rundzie" in kval_rank.columns:
        kval_rank.rename(columns={"Miejsce w rundzie":"Miejsce"}, inplace=True)
        
    # Odl.Q jako kopia odległości (jeśli chcesz mieć tę kolumnę)
    if "Odległość" in kval_rank.columns and "Odl.Q" not in kval_rank.columns:
        kval_rank["Odl.Q"] = kval_rank["Odległość"]

    # Sort + miejsca ex aequo (Kwalifikacje)
    kval_rank = kval_rank.sort_values("Punkty", ascending=False).reset_index(drop=True)
    kval_rank = _apply_tied_places(kval_rank, points_col="Punkty", place_col="Miejsce", ascending=False)

    # (opcjonalnie) odchudzenie kolumn dla KO64:
    wanted_cols = ["Miejsce","Zawodnik","Kraj","Odl.Q","Punkty"]
    kval_rank = kval_rank[[c for c in wanted_cols if c in kval_rank.columns]].copy()
        
    # 🔽 Ogranicz kolumny w Klasyfikacji kwal. do tylko kilku potrzebnych
    wanted_cols = ["Miejsce", "Zawodnik", "Kraj", "Odl.Q", "Punkty"]

    # Dodaj kolumnę Odl.Q (kopię Odległość)
    if "Odległość" in kval_rank.columns and "Odl.Q" not in kval_rank.columns:
         kval_rank["Odl.Q"] = kval_rank["Odległość"]

    # Upewnij się, że wszystkie kolumny istnieją
    kval_rank = kval_rank[[c for c in wanted_cols if c in kval_rank.columns]].copy()

    # 1) Top64 z kwalifikacji
    field = _prep_field(kval_rank, 64)

    # 2) Dołącz brakujące UM/Forma/Kraj z rosteru (jeżeli trzeba)
    need_cols = {"UM", "Forma"}
    if not need_cols.issubset(set(field.columns)):
        base_cols = [c for c in ["Zawodnik","UM","Forma","Kraj"] if c in roster.columns]
        base_df = roster[base_cols].copy()
        if "Zawodnik" in base_df.columns:
            base_df["__key"] = base_df["Zawodnik"].map(_norm_name_key)
            base_df = base_df.drop_duplicates(subset=["__key"], keep="first").drop(columns=["__key"])
        field = field.merge(base_df, on="Zawodnik", how="left", suffixes=("", "_src"))
        if "Kraj" not in field.columns and "Kraj_src" in field.columns:
            field.rename(columns={"Kraj_src": "Kraj"}, inplace=True)
        elif "Kraj_src" in field.columns:
            field.drop(columns=["Kraj_src"], inplace=True)

    # 3) Dopełnij BYE do 64 seedów i ustaw stały układ R1
    field = _fill_byes_to_64(field, 64)
    seed_order = _bracket_seed_order(64)
    current = field.set_index('Seed').loc[seed_order].reset_index()[["Seed","Zawodnik","UM","Forma","Kraj","IsBYE"]]
    
    # normalizacja IsBYE: stringi "False"/"True" → bool
    if "IsBYE" not in current.columns:
        current["IsBYE"] = False
    current["IsBYE"] = current["IsBYE"].apply(_to_bool)
    current.loc[current["Zawodnik"].astype(str).str.match(BYE_NAME_RE), "IsBYE"] = True
    current.loc[current["Kraj"].astype(str).str.upper().eq("BYE"), "IsBYE"] = True


    # ——— dodatkowy detektor BYE (obok kolumny IsBYE) ———
    # ↑ w nagłówkach pliku masz już: import re as _re   (lub import re)

    def _is_bye_row(rec):
        name = str(rec.get("Zawodnik",""))
        kraj = str(rec.get("Kraj",""))
        if _to_bool(rec.get("IsBYE", False)): return True
        if BYE_NAME_RE.match(name):           return True   # "BYE", "[BYE]", "BYE 43"
        if kraj.strip().upper() == "BYE":     return True
        return False

    # ---- Zbieranie Odl1..Odl6 + suma ----
    agg = {}
    falls_acc = []
    def ensure_row(name, kraj):
        if name not in agg:
            agg[name] = {"Zawodnik": name, "Kraj": kraj, "Odl1": None, "Odl2": None, "Odl3": None, "Odl4": None, "Odl5": None, "Odl6": None, "Punkty": 0.0}

    bracket_rows = []
    contest_all = []
    round_num = 1
    while len(current) >= 2:
        n = len(current)
        pairs = _pair_indices(n)
        rows_this_round = []
        winners_rows = []
        for pid, (i, j) in enumerate(pairs, start=1):
            A = current.iloc[i]; B = current.iloc[j]
            a_is_bye = _is_bye_row(A)
            b_is_bye = _is_bye_row(B)

            if a_is_bye or b_is_bye:
                # walkower – tak jak masz
                def mkrow(rec):
                    return {"Zawodnik": rec["Zawodnik"], "UM": rec.get("UM", np.nan),
                            "Forma": rec.get("Forma", np.nan), "Kraj": rec.get("Kraj",""),
                            "Odległość (m)": np.nan, "Odległość": "", "Noty stylowe": 0.0,
                            "Punkty za odległość": 0.0, "Kompensacja wiatru": 0.0,
                            "Kompensacja belki": 0.0, "Punkty rundy": 0.0, "Punkty": "0.0",
                            "Upadek": False}
                row_a = mkrow(A); row_b = mkrow(B)
            else:
                # sanity: liczby dla UM/Forma
                pair = current.loc[[i, j], ["Zawodnik","UM","Forma","Kraj"]].copy()
                pair["UM"]    = pd.to_numeric(pair["UM"], errors="coerce").fillna(0.0)
                pair["Forma"] = pd.to_numeric(pair["Forma"], errors="coerce").fillna(0.0)

                def _run_pair(pair_df, sort_out):
                    return sim.simulate_round(
                        roster=pair_df,
                        K=K, HS=HS, meter_value=meter_value,
                        wind_ms_mean=wind_ms_mean, wind_ms_sd=wind_ms_sd,
                        gate_base=gate_base, gate_points_per_step=gate_points_per_step,
                        p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
                        rng=rng, randomness=randomness, elite_regress=elite_regress,
                        wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
                        wind_flight_gain=wind_flight_gain, judges_rho=judges_rho,
                        sort_output=sort_out,
                    )

                try:
                    # preferowane: zachowaj kolejność A/B
                    r_pair = _run_pair(pair, sort_out=False)
                    print(f"DEBUG R{round_num} pid={pid}: Upadek raw={r_pair['Upadek'].tolist()}, dtype={r_pair['Upadek'].dtype}")
                
                    # NOWE: normalizuj kolumnę Upadek do bool
                    if "Upadek" in r_pair.columns:
                        r_pair["Upadek"] = r_pair["Upadek"].apply(_to_bool)
                    else:
                        r_pair["Upadek"] = False
                except Exception:
                    # retry: unikamy crasha rank() na NaN
                    r_pair = _run_pair(pair, sort_out=True)
                    # przywróć kolejność: A, potem B
                    r_pair = (r_pair
                            .set_index("Zawodnik")
                            .reindex([A["Zawodnik"], B["Zawodnik"]])
                            .reset_index())

                # Awaryjnie wyczyść NaN w punktach / odległościach
                if "Punkty rundy" in r_pair.columns:
                    r_pair["Punkty rundy"] = pd.to_numeric(r_pair["Punkty rundy"], errors="coerce").fillna(0.0)
                # 1) odległość liczbowo + kolumna tekstowa
                if "Odległość (m)" in r_pair.columns:
                    r_pair["Odległość (m)"] = pd.to_numeric(r_pair["Odległość (m)"], errors="coerce")
                else:
                    r_pair["Odległość (m)"] = np.nan
                if "Odległość" not in r_pair.columns:
                    r_pair["Odległość"] = r_pair["Odległość (m)"].map(lambda v: "" if pd.isna(v) else f"{float(v):.2f}m")

                # -- po: r_pair["Odległość (m)"] ... oraz utworzeniu r_pair["Odległość"] --
                # Upewnij się, że są punkty za odległość – jeśli brak/zero, policz z K i meter_value
                mv = meter_value if meter_value is not None else sim.compute_meter_value(K)
                base_pts = 120.0 if (K is not None and K >= 160) else 60.0

                if "Punkty za odległość" not in r_pair.columns:
                    r_pair["Punkty za odległość"] = 0.0

                dist_num = pd.to_numeric(r_pair["Odległość (m)"], errors="coerce")
                dist_pts = base_pts + (dist_num - float(K)) * float(mv)
                # Zastąp tylko tam, gdzie jest NaN lub 0.0
                mask_fix = r_pair["Punkty za odległość"].fillna(0.0).eq(0.0) & dist_num.notna()
                r_pair.loc[mask_fix, "Punkty za odległość"] = dist_pts.round(1).fillna(0.0)


                # 2) upewnij się, że są wszystkie składowe punktów
                need = ["Punkty za odległość","Noty stylowe","Kompensacja wiatru","Kompensacja belki"]
                for col in need:
                    if col not in r_pair.columns:
                        r_pair[col] = 0.0
                    r_pair[col] = pd.to_numeric(r_pair[col], errors="coerce").fillna(0.0)

                r_pair["Punkty rundy"] = r_pair[need].sum(axis=1).astype(float)

                # 4) jeżeli trzeba – przywróć kolejność A/B (po ewentualnym retry z sort_output=True)
                if list(r_pair["Zawodnik"]) != [A["Zawodnik"], B["Zawodnik"]]:
                    r_pair = (r_pair.set_index("Zawodnik")
                                    .reindex([A["Zawodnik"], B["Zawodnik"]])
                                    .reset_index())

                row_a = r_pair.iloc[0].to_dict()
                row_b = r_pair.iloc[1].to_dict()

                def _fmt_pts(x: float) -> str:
                    try:
                        return f"{float(x):.1f}"
                    except Exception:
                        return "0.0"

                # zaokrąglenie wartości liczbowej i przygotowanie wersji tekstowej
                for row in (row_a, row_b):
                    pts_num = float(row.get("Punkty rundy", 0.0))
                    pts_num = round(pts_num, 1)
                    row["Punkty rundy"] = pts_num          # liczba – używana w logice
                    row["Punkty"] = _fmt_pts(pts_num)      # tekst – do wyświetlenia w tabeli

                pa = float(row_a["Punkty rundy"])
                pb = float(row_b["Punkty rundy"])


            row_a.update({"Seed": int(A["Seed"]), "Para": pid, "Runda": round_num})
            row_b.update({"Seed": int(B["Seed"]), "Para": pid, "Runda": round_num})
            rows_this_round.extend([row_a, row_b])

            # --- KO64: agregacja do tabeli "KO64 - Klasyfikacja" (Odl1..Odl6 + suma punktów) ---
            ensure_row(A["Zawodnik"], A.get("Kraj",""))
            ensure_row(B["Zawodnik"], B.get("Kraj",""))

            slot_map = {1:"Odl1", 2:"Odl2", 3:"Odl3", 4:"Odl4", 5:"Odl5", 6:"Odl6"}
            slot = slot_map.get(round_num)

            def _odl_val(row):
                # Preferujemy gotową kolumnę tekstową; jeśli brak – format z (m)
                if str(row.get("Odległość", "")).strip():
                    return row.get("Odległość")
                val = row.get("Odległość (m)", None)
                try:
                    return None if pd.isna(val) else f"{float(val):.2f}m"
                except Exception:
                    return None

            if slot:
                agg[A["Zawodnik"]][slot] = _odl_val(row_a)
                agg[B["Zawodnik"]][slot] = _odl_val(row_b)

            # Sumuj punkty z całych zawodów
            agg[A["Zawodnik"]]["Punkty"] = float(agg[A["Zawodnik"]]["Punkty"]) + float(row_a.get("Punkty rundy", 0.0) or 0.0)
            agg[B["Zawodnik"]]["Punkty"] = float(agg[B["Zawodnik"]]["Punkty"]) + float(row_b.get("Punkty rundy", 0.0) or 0.0)

            def _num(x):
                try:
                    return float(x)
                except Exception:
                    return 0.0

            def _recalc_points(d: dict) -> float:
                # 1) bierz to co jest, jeśli liczba i > 0
                v = d.get("Punkty rundy", None)
                try:
                    v = float(v)
                except Exception:
                    v = float("nan")
                # 2) jeśli brak/NaN/albo 0.0, a są dane składowe – przelicz
                if (pd.isna(v) or v == 0.0):
                    comp = (_num(d.get("Punkty za odległość"))
                            + _num(d.get("Noty stylowe"))
                            + _num(d.get("Kompensacja wiatru"))
                            + _num(d.get("Kompensacja belki")))
                    # jeśli suma składowych wygląda sensownie, użyj jej
                    if comp != 0.0 or _num(d.get("Odległość (m)")) > 0.0:
                        v = comp if not pd.isna(comp) else 0.0
                return float(v if not pd.isna(v) else 0.0)

            # --- tu liczymy punkty bezpiecznie ---
            pa = _recalc_points(row_a)
            pb = _recalc_points(row_b)

            # dopisz z powrotem do rekordów (żeby był spójny zapis w tabelach/arkuszach)
            row_a["Punkty rundy"] = pa
            row_b["Punkty rundy"] = pb


            # wybór zwycięzcy
            if a_is_bye and not b_is_bye:
                win = B
            elif b_is_bye and not a_is_bye:
                win = A
            elif a_is_bye and b_is_bye:
                # BYE vs BYE → przechodzi niższy seed, ale to wciąż BYE
                win = A if int(A["Seed"]) < int(B["Seed"]) else B
            else:
                win = A if (pa > pb or (pa == pb and int(A["Seed"]) < int(B["Seed"]))) else B

            # IsBYE zwycięzcy: tylko gdy to rzeczywiście BYE (czyli para BYE vs BYE)
            winner_is_bye = a_is_bye and b_is_bye

            winners_rows.append({
                "Seed": int(win["Seed"]),
                "Zawodnik": win["Zawodnik"],
                "UM": win.get("UM", np.nan),
                "Forma": win.get("Forma", np.nan),
                "Kraj": win.get("Kraj",""),
                "IsBYE": (a_is_bye and b_is_bye)
            })

            bracket_rows.append({
                "Runda": _round_label(round_num), "Para": pid,
                "Seed A": int(A["Seed"]), "Zawodnik A": A["Zawodnik"], "Kraj A": A.get("Kraj",""),
                "Odl A (m)": row_a.get("Odległość (m)", np.nan), "Punkty A": pa,
                "Seed B": int(B["Seed"]), "Zawodnik B": B["Zawodnik"], "Kraj B": B.get("Kraj",""),
                "Odl B (m)": row_b.get("Odległość (m)", np.nan), "Punkty B": pb,
                "Zwycięzca (Seed)": int(win["Seed"]), "Zwycięzca": win["Zawodnik"],
            })

        contest_all.append(pd.DataFrame(rows_this_round))
        contest_all[-1]["Upadek"] = contest_all[-1]["Upadek"].fillna(False).apply(_to_bool)
        rnd_df = contest_all[-1]
        print(f"DEBUG contest R{round_num-1}: Upadek={rnd_df['Upadek'].tolist() if 'Upadek' in rnd_df.columns else 'BRAK'}")
        if "Upadek" in rnd_df.columns:
            fallen = rnd_df[rnd_df["Upadek"].apply(_to_bool)].copy()
            if not fallen.empty:
                fallen["Runda"] = f"KO-R{round_num - 1}"
                falls_acc.append(fallen)
        
        current = pd.DataFrame(winners_rows).reset_index(drop=True)
        round_num += 1

    # eliminacje do miejsc
    elim_groups = {}
    for r_df in contest_all:
        r = int(r_df["Runda"].iloc[0])
        losers = []
        for pid, g in r_df.groupby("Para", sort=True):
            g = g.reset_index(drop=True)
            if len(g) < 2:
                # WO – brak przegranego w tej parze
                continue
            a, b = g.iloc[0], g.iloc[1]
            pa = float(a["Punkty rundy"]); pb = float(b["Punkty rundy"])
            loser = b if (pa > pb or (pa == pb and int(a["Seed"]) < int(b["Seed"]))) else a
            losers.append(loser)
        elim_groups[r] = pd.DataFrame(losers)

    final_df = contest_all[-1]
    a = final_df.iloc[0]; b = final_df.iloc[1]
    pa = float(a["Punkty rundy"]); pb = float(b["Punkty rundy"])
    champ, vice = (a, b) if (pa > pb or (pa == pb and int(a["Seed"]) < int(b["Seed"]))) else (b, a)

    def _sort_group(df):
        df = df.copy()
        df["__pts"] = pd.to_numeric(df["Punkty rundy"], errors="coerce").fillna(0.0)
        df["__seed"] = pd.to_numeric(df["Seed"], errors="coerce").fillna(9999)
        return df.sort_values(["__pts","__seed"], ascending=[False, True]).drop(columns=["__pts","__seed"])

    klasyf_rows = [
        {"Miejsce":1,"Zawodnik":champ["Zawodnik"],"Kraj":champ.get("Kraj",""),"Seed":int(champ["Seed"]),"Punkty":float(champ["Punkty rundy"])},
        {"Miejsce":2,"Zawodnik":vice["Zawodnik"],"Kraj":vice.get("Kraj",""),"Seed":int(vice["Seed"]),"Punkty":float(vice["Punkty rundy"])}
    ]
    if 5 in elim_groups:
        g=_sort_group(elim_groups[5]).reset_index(drop=True)
        for i,row in g.iterrows():
            klasyf_rows.append({"Miejsce":3+i,"Zawodnik":row["Zawodnik"],"Kraj":row.get("Kraj",""),"Seed":int(row["Seed"]),"Punkty":float(row["Punkty rundy"])})
    if 4 in elim_groups:
        g=_sort_group(elim_groups[4]).reset_index(drop=True)
        for i,row in g.iterrows():
            klasyf_rows.append({"Miejsce":5+i,"Zawodnik":row["Zawodnik"],"Kraj":row.get("Kraj",""),"Seed":int(row["Seed"]),"Punkty":float(row["Punkty rundy"])})
    if 3 in elim_groups:
        g=_sort_group(elim_groups[3]).reset_index(drop=True)
        for i,row in g.iterrows():
            klasyf_rows.append({"Miejsce":9+i,"Zawodnik":row["Zawodnik"],"Kraj":row.get("Kraj",""),"Seed":int(row["Seed"]),"Punkty":float(row["Punkty rundy"])})
    if 2 in elim_groups:
        g=_sort_group(elim_groups[2]).reset_index(drop=True)
        for i,row in g.iterrows():
            klasyf_rows.append({"Miejsce":17+i,"Zawodnik":row["Zawodnik"],"Kraj":row.get("Kraj",""),"Seed":int(row["Seed"]),"Punkty":float(row["Punkty rundy"])})
    if 1 in elim_groups:
        g=_sort_group(elim_groups[1]).reset_index(drop=True)
        for i,row in g.iterrows():
            klasyf_rows.append({"Miejsce":33+i,"Zawodnik":row["Zawodnik"],"Kraj":row.get("Kraj",""),"Seed":int(row["Seed"]),"Punkty":float(row["Punkty rundy"])})
            
        klasyf = pd.DataFrame(klasyf_rows)
        # sort wyświetlania – np. po 'Punkty' desc i ewentualnie 'Seed' asc (stabilnie)
        if "Punkty" in klasyf.columns:
            klasyf["Punkty"] = pd.to_numeric(klasyf["Punkty"], errors="coerce").fillna(0.0)
        by = ["Punkty", "Seed"] if "Seed" in klasyf.columns else ["Punkty"]
        asc = [False, True] if "Seed" in klasyf.columns else [False]
        klasyf = klasyf.sort_values(by=by, ascending=asc, kind="stable").reset_index(drop=True)

        # miejsca ex aequo
        klasyf = _apply_tied_places(klasyf, points_col="Punkty", place_col="Miejsce", ascending=False)

        # -- KO64 - Klasyfikacja (Odl1..Odl6 + Punkty) posortowana po własnych punktach
        
        detailed = pd.DataFrame(agg.values())
        cols = ["Zawodnik","Kraj","Odl1","Odl2","Odl3","Odl4","Odl5","Odl6","Punkty"]
        detailed = detailed[[c for c in cols if c in detailed.columns]]
        if "Punkty" not in detailed.columns:
            detailed["Punkty"] = 0.0
        if "Punkty" in detailed.columns:
            detailed["Punkty"] = pd.to_numeric(detailed["Punkty"], errors="coerce").fillna(0.0)
        # sort po SUMIE punktów z całych zawodów
        # KO64: remis w Punktach → wspólne Miejsce, ale kolejność w remisie po NAJWIĘKSZEJ odległości (Odl1..Odl6)
        odl_cols = [c for c in ["Odl1","Odl2","Odl3","Odl4","Odl5","Odl6"] if c in detailed.columns]

        if odl_cols:
            def _to_num(sr):
                return pd.to_numeric(
                    sr.astype(str)
                    .str.replace("*","", regex=False)
                    .str.replace("~","", regex=False)
                    .str.replace(",", ".", regex=False),
                    errors="coerce"
                )
            _dist = pd.concat([_to_num(detailed[c]).rename(c) for c in odl_cols], axis=1)
            detailed["__maxd"] = _dist.sum(axis=1).fillna(-1e9)
            detailed = (
                detailed
                .sort_values(["Punkty","__maxd"], ascending=[False, False], kind="mergesort")
                .drop(columns="__maxd")
                .reset_index(drop=True)
            )
        else:
            detailed = detailed.sort_values("Punkty", ascending=False, kind="mergesort").reset_index(drop=True)

        # miejsca ex aequo (1,1,3…)
        detailed = _apply_tied_places(detailed, points_col="Punkty", place_col="Miejsce", ascending=False)

        # --- WYJĄTEK: finał – po punktach z finału decydujemy o 1/2 miejscu ---
        try:
            champ_name = str(champ.get("Zawodnik","")).strip()
            vice_name = str(vice.get("Zawodnik","")).strip()
            if champ_name and vice_name and champ_name in list(detailed["Zawodnik"]) and vice_name in list(detailed["Zawodnik"]):
                # Weź wiersze finalistów (zachowujemy ich SUMY w kolumnie 'Punkty', zmieniamy tylko kolejność miejsc)
                det = detailed.set_index("Zawodnik")
                # Usuń finalistów z tabeli i na końcu wstaw ich na 1 i 2 miejsce
                others = det.drop(index=[champ_name, vice_name], errors="ignore").reset_index()
                # Finalistów dokładamy na początek (1,2) – kolejność zgodnie z champ/vice (ustalone po punktach finału wcześniej)
                top2 = pd.DataFrame([
                    {"Miejsce": 1, "Zawodnik": champ_name, "Kraj": det.at[champ_name, "Kraj"] if champ_name in det.index else "", 
                     "Odl1": det.at[champ_name, "Odl1"] if "Odl1" in det.columns and champ_name in det.index else None,
                     "Odl2": det.at[champ_name, "Odl2"] if "Odl2" in det.columns and champ_name in det.index else None,
                     "Odl3": det.at[champ_name, "Odl3"] if "Odl3" in det.columns and champ_name in det.index else None,
                     "Odl4": det.at[champ_name, "Odl4"] if "Odl4" in det.columns and champ_name in det.index else None,
                     "Odl5": det.at[champ_name, "Odl5"] if "Odl5" in det.columns and champ_name in det.index else None,
                     "Odl6": det.at[champ_name, "Odl6"] if "Odl6" in det.columns and champ_name in det.index else None,
                     "Punkty": det.at[champ_name, "Punkty"] if champ_name in det.index else 0.0},
                    {"Miejsce": 2, "Zawodnik": vice_name, "Kraj": det.at[vice_name, "Kraj"] if vice_name in det.index else "", 
                     "Odl1": det.at[vice_name, "Odl1"] if "Odl1" in det.columns and vice_name in det.index else None,
                     "Odl2": det.at[vice_name, "Odl2"] if "Odl2" in det.columns and vice_name in det.index else None,
                     "Odl3": det.at[vice_name, "Odl3"] if "Odl3" in det.columns and vice_name in det.index else None,
                     "Odl4": det.at[vice_name, "Odl4"] if "Odl4" in det.columns and vice_name in det.index else None,
                     "Odl5": det.at[vice_name, "Odl5"] if "Odl5" in det.columns and vice_name in det.index else None,
                     "Odl6": det.at[vice_name, "Odl6"] if "Odl6" in det.columns and vice_name in det.index else None,
                     "Punkty": det.at[vice_name, "Punkty"] if vice_name in det.index else 0.0},
                ])
                # Miejsca dla pozostałych przesuwamy tak, aby zaczynały się od 3 z ex aequo po sumie
                others = _apply_tied_places(others, points_col="Punkty", place_col="Miejsce", ascending=False)
                others["Miejsce"] = others["Miejsce"].astype(int) + 2
                detailed = pd.concat([top2, others[top2.columns]], ignore_index=True)
        except Exception as _e:
            pass


        # -- reszta bez zmian
        contest_rows = pd.concat(contest_all, ignore_index=True)
        print("DEBUG contest_rows columns:", list(contest_rows.columns))
        print("DEBUG contest_rows Upadek sample:", contest_rows["Upadek"].value_counts() if "Upadek" in contest_rows.columns else "BRAK KOLUMNY")
        print("DEBUG contest_rows Runda sample:", contest_rows["Runda"].unique() if "Runda" in contest_rows.columns else "BRAK KOLUMNY")
        bracket_df = pd.DataFrame(bracket_rows)
        # Złóż upadki ze wszystkich rund KO64
        if falls_acc:
            falls_df = pd.concat(falls_acc, ignore_index=True)
            # Zachowaj tylko kolumny które ma standardowa tabela upadków
            keep_cols = [c for c in (
                "Runda", "Zawodnik", "Kraj", "Odległość (m)", "Odległość",
                "Upadek", "Punkty rundy"
            ) if c in falls_df.columns]
            falls_df = falls_df[keep_cols].copy()
        else:
            falls_df = pd.DataFrame(columns=["Runda", "Zawodnik", "Kraj", "Odległość"])

        extra_sheets = {
            "KO64 - Drabinka":     bracket_df,
            "KO64 - Klasyfikacja": detailed,
            "Upadki":              falls_df,   # <-- NOWE
        }
        return kwal_df, kval_rank, contest_rows, klasyf, extra_sheets

def _prepare_falls_df_for_gui(df):
    """Gwarantuje wyświetlenie wszystkich kolumn medycznych w tabeli Upadki."""
    
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    
    # Lista kolumn w pożądanej kolejności
    desired = [
        "Runda", "Zawodnik", "Sex", "Kraj", "Lekarz", "Infrastruktura", 
        "Odległość", "Kontuzja (rodzaj)", "Kontuzja (dni)", 
        "Długość kontuzji (WEEK)", "ΔUM (kontuzja)", "ΔForma (kontuzja)"
    ]
    
    # Sprawdź, które z nich faktycznie istnieją w DF
    existing_cols = [c for c in desired if c in out.columns]
    # Dodaj resztę, której nie ma na liście (na wszelki wypadek)
    rest = [c for c in out.columns if c not in existing_cols]
    
    final_cols = existing_cols + rest
    
    try:
        # Konwersja typów dla ładnego wyświetlania (bez .0 przy liczbach)
        for col in ["Kontuzja (dni)", "Lekarz", "Infrastruktura", "Długość kontuzji (WEEK)", "ΔUM (kontuzja)", "ΔForma (kontuzja)"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    except Exception:
        pass
        
    return out[final_cols]

# ==================== GUI ====================
def build_gui(parent):
    return MainFrame(parent)

class MainFrame(ttk.Frame):
    def _update_classifications_from_preview(self, season: str, cycle: str):
        """
        Aktualizuje pliki klasyfikacji na podstawie ostatnio wyświetlonej klasyfikacji końcowej.
        Sezon: 'S45'; Cykl: 'WC-M', 'COC-W', ...
        Zapis:
        - {season}_{cycle}__players.csv   (LP.,JUMPER,NAT,PTS)
        - {season}_{cycle}__nations.csv   (WC-*: LP.,NATION,NAT,T,I,PTS; else: LP.,NATION,NAT,PTS)
        Zwraca: (liczba_wierszy_players, liczba_wierszy_nations, folder_klasyfikacji)
        """
        
        # LP. z obsługą remisów: przy równych PTS/1/2/3 → to samo miejsce
        def _reindex_lp_local(df):
            if "LP." in df.columns:
                df = df.drop(columns=["LP."])
            tie_cols = [c for c in ["PTS","1","2","3"] if c in df.columns]
            if tie_cols:
                # rank(method="min") → przy remisie obaj dostają niższe miejsce
                lp = df[tie_cols].apply(pd.to_numeric, errors="coerce").fillna(0)\
                       .apply(tuple, axis=1)\
                       .rank(method="min", ascending=False).astype(int)
            else:
                lp = range(1, len(df) + 1)
            df.insert(0, "LP.", lp)
            return df

        # --- mapowanie NAT -> pełna nazwa kraju (np. "KAZ" -> "Kazachstan")
        def _nat_name_map() -> dict:
            # podstawowy, krótki fallback (dopisz, jeśli czegoś brakuje)
            base = {
                "KAZ":"Kazachstan", "JPN":"Japonia", "AUT":"Austria", "CZE":"Czechy",
                "SLO":"Słowenia", "FIN":"Finlandia", "BUL":"Bułgaria", "USA":"USA",
                "GER":"Niemcy", "ITA":"Włochy", "RUS":"Rosja", "SUI":"Szwajcaria",
                "NOR":"Norwegia", "CAN":"Kanada", "EST":"Estonia", "GBR":"Wielka Brytania",
                "MHL":"Wyspy Marshalla",
                # …dopisz według potrzeb
            }
            # spróbuj dociągnąć większą mapę z modułu team GUI (jeśli masz)
            try:
                from team_competition_gui_embedded import TEAM_NAME as _MAP
                for k, v in _MAP.items():
                    base.setdefault(str(k).upper(), str(v))
            except Exception:
                pass
            # spróbuj wyczytać z „Infrastruktura S45.csv”, jeśli ma kolumnę z nazwą
            try:
                df = _read_tab_any(_find_nearby_file("Infrastruktura S45.csv",
                                alt_patterns=["*Infrastruktura* S45*.csv", "*Infrastruktura*.csv"]))
                if df is not None:
                    nat_col = _col(df, ["KRAJ","NAT","Kod","Country"])
                    name_col= _col(df, ["REPREZENTACJA","Reprezentacja","Country Name","Kraj (pełna nazwa)"], prefix_ok=True)
                    if nat_col and name_col:
                        for _, r in df.iterrows():
                            k = str(r.get(nat_col, "")).strip().upper()
                            nm = str(r.get(name_col, "")).strip()
                            if k and nm and k not in base:
                                base[k] = nm
            except Exception:
                pass
            return base
            
        # --- skąd bierzemy punkty z konkursu ---
        df = getattr(self, "_last_final_cls", None)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            raise RuntimeError("Brak danych finału w Podglądzie. Najpierw uruchom konkurs.")

        # Normalizacja kluczowych kolumn
        d = df.copy()
        for c in ("Zawodnik", "Kraj"):
            if c not in d.columns:
                raise RuntimeError(f"Klasyfikacja końcowa nie zawiera kolumny: {c}")
        # Preferuj kolumnę „Punkty FIS”; jeśli brak – wylicz ze skali 100-80-60-...-1 po „Miejsce”
        if "Punkty FIS" in d.columns:
            pts = pd.to_numeric(d["Punkty FIS"], errors="coerce").fillna(0).astype(float)
        else:
            # fallback: skala FIS dla TOP30
            scale = [100,80,60,50,45,40,36,32,29,26,24,22,20,18,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1]
            m = pd.to_numeric(d.get("Miejsce", None), errors="coerce")
            pts = m.map(lambda x: scale[int(x)-1] if pd.notna(x) and 1 <= int(x) <= len(scale) else 0)
        d = d.assign(__PTS__=pd.to_numeric(pts, errors="coerce").fillna(0.0))

        # Ścieżki plików wg Twojej konwencji
        root = Path(f"./{season}/Klasyfikacje {season}").resolve()
        root.mkdir(parents=True, exist_ok=True)
        players_path = root / f"{season}_{cycle}__players.csv"
        nations_path = root / f"{season}_{cycle}__nations.csv"

        # ---------- pomocnicze I/O ----------
        def _read_csv_loose(p: Path) -> pd.DataFrame:
            if not p.exists():
                return pd.DataFrame()
            # sep=None + engine="python" → pandas sam wykrywa separator
            for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
                try:
                    tmp = pd.read_csv(p, sep=None, engine="python", encoding=enc)
                    if not tmp.empty and len(tmp.columns) >= 2:
                        return tmp
                except Exception:
                    continue
            # fallback: jawnie średnik
            try:
                return pd.read_csv(p, sep=";", encoding="utf-8-sig")
            except Exception:
                return pd.DataFrame()

        def _write_csv_utf8(p: Path, df_out: pd.DataFrame):
            # bez indeksu, z BOM dla wygody w Excelu
            df_out.to_csv(p, index=False, encoding="utf-8-sig", sep=";")

        # ---------- PLAYERS ----------
        cur_p = _read_csv_loose(players_path)
        # Upewnij się w nagłówkach: LP.,JUMPER,NAT,PTS oraz nowe 1, 2, 3
        req_cols = ["LP.","JUMPER","NAT","PTS","1","2","3"]
        if cur_p.empty or not set(["LP.","JUMPER","NAT","PTS"]).issubset({str(c) for c in cur_p.columns}):
            cur_p = pd.DataFrame(columns=req_cols)

        # Dodaj brakujące kolumny 1,2,3 jeśli plik ich jeszcze nie ma
        for c in ["1", "2", "3"]:
            if c not in cur_p.columns:
                cur_p[c] = 0

        add_p = d[["Zawodnik","Kraj","__PTS__","Miejsce"]].copy()
        add_p.rename(columns={"Zawodnik":"JUMPER","Kraj":"NAT","__PTS__":"__ADD__"}, inplace=True)

        # Przygotuj kolumny zwycięstw dla nowych wyników
        add_p["1_add"] = (add_p["Miejsce"] == 1).astype(int)
        add_p["2_add"] = (add_p["Miejsce"] == 2).astype(int)
        add_p["3_add"] = (add_p["Miejsce"] == 3).astype(int)

        # merge po (JUMPER,NAT)
        base = cur_p.copy()
        base["PTS"] = pd.to_numeric(base.get("PTS", 0), errors="coerce").fillna(0.0)
        for c in ["1","2","3"]:
            base[c] = pd.to_numeric(base.get(c, 0), errors="coerce").fillna(0).astype(int)

        merged = base.merge(add_p, on=["JUMPER","NAT"], how="outer").fillna(0)
        merged["PTS"] = merged["PTS"] + merged["__ADD__"]
        merged["1"] = merged["1"] + merged["1_add"]
        merged["2"] = merged["2"] + merged["2_add"]
        merged["3"] = merged["3"] + merged["3_add"]

        merged.drop(columns=["__ADD__", "Miejsce", "1_add", "2_add", "3_add"], inplace=True)

        # ustaw LP. wg PTS malejąco; remis: 1. miejsc > 2. miejsc > 3. miejsc > nazwa
        merged = merged.sort_values(["PTS","1","2","3","JUMPER"], ascending=[False,False,False,False,True], kind="mergesort").reset_index(drop=True)
        merged = _reindex_lp_local(merged)
        _write_csv_utf8(players_path, merged)
        n_players = len(merged)

        # ---------- NATIONS ----------
        # SKI_FLYING nie ma klasyfikacji drużynowej – zapisujemy tylko players
        if cycle.strip().upper().startswith("SKI_FLYING"):
            return n_players, 0, str(root)

        cur_n = _read_csv_loose(nations_path)
        wc_like = bool(re.match(r"^(WC|GP)-", cycle.strip().upper()))
        if wc_like:
            needed = ["LP.","NATION","NAT","T","I","PTS","1","2","3"]
            if cur_n.empty or not set(["LP.","NATION","NAT","T","I","PTS"]).issubset({str(c) for c in cur_n.columns}):
                cur_n = pd.DataFrame(columns=needed)
            for c in ("T","I","PTS","1","2","3"):
                if c not in cur_n.columns:
                    cur_n[c] = 0
            # punkty z konkursu sumujemy per kraj → do I (1/2/3 aktualizowane przez drużynówkę)
            add_n = d.groupby("Kraj", dropna=False)["__PTS__"].sum().reset_index()
            add_n.rename(columns={"Kraj":"NAT","__PTS__":"__ADD__"}, inplace=True)
            base_n = cur_n.copy()
            for c in ("T","I","PTS","1","2","3"):
                base_n[c] = pd.to_numeric(base_n.get(c, 0), errors="coerce").fillna(0.0)
            merged_n = base_n.merge(add_n, on="NAT", how="outer")
            merged_n["I"] = pd.to_numeric(merged_n["I"], errors="coerce").fillna(0.0) + pd.to_numeric(merged_n["__ADD__"], errors="coerce").fillna(0.0)
            merged_n["T"] = pd.to_numeric(merged_n["T"], errors="coerce").fillna(0.0)
            merged_n["PTS"] = merged_n["T"] + merged_n["I"]
            for c in ("1","2","3"):
                merged_n[c] = pd.to_numeric(merged_n[c], errors="coerce").fillna(0).astype(int)
            merged_n.drop(columns=["__ADD__"], inplace=True, errors="ignore")
            merged_n = merged_n.fillna({"NATION":"", "NAT":""})
            nat2name = _nat_name_map()
            mask_empty = (
                merged_n["NATION"].astype(str).str.strip().eq("") |
                merged_n["NATION"].astype(str).str.lower().eq("nan")
            )
            merged_n.loc[mask_empty, "NATION"] = (
                merged_n.loc[mask_empty, "NAT"].astype(str).str.upper().map(nat2name)
                    .fillna(merged_n.loc[mask_empty, "NATION"])
            )

            merged_n = merged_n.sort_values(["PTS","1","2","3","NATION"], ascending=[False,False,False,False,True], kind="mergesort").reset_index(drop=True)
            merged_n = _reindex_lp_local(merged_n)
        else:
            needed = ["LP.","NATION","NAT","PTS"]
            if cur_n.empty or not set(needed).issubset({str(c) for c in cur_n.columns}):
                cur_n = pd.DataFrame(columns=needed)
            base_n = cur_n.copy()
            base_n["PTS"] = pd.to_numeric(base_n.get("PTS", 0), errors="coerce").fillna(0.0)
            add_n = d.groupby("Kraj", dropna=False)["__PTS__"].sum().reset_index()
            add_n.rename(columns={"Kraj":"NAT","__PTS__":"__ADD__"}, inplace=True)
            merged_n = base_n.merge(add_n, on="NAT", how="outer")
            merged_n["PTS"] = pd.to_numeric(merged_n["PTS"], errors="coerce").fillna(0.0) + pd.to_numeric(merged_n["__ADD__"], errors="coerce").fillna(0.0)
            merged_n.drop(columns=["__ADD__"], inplace=True)
            merged_n = merged_n.fillna({"NATION":"", "NAT":""})
            nat2name = _nat_name_map()
            mask_empty = (
                merged_n["NATION"].astype(str).str.strip().eq("") |
                merged_n["NATION"].astype(str).str.lower().eq("nan")
            )
            merged_n.loc[mask_empty, "NATION"] = (
                merged_n.loc[mask_empty, "NAT"].astype(str).str.upper().map(nat2name)
                    .fillna(merged_n.loc[mask_empty, "NATION"])
            )

            merged_n = merged_n.sort_values(["PTS","NATION"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
            merged_n = _reindex_lp_local(merged_n)

        _write_csv_utf8(nations_path, merged_n)
        n_nations = len(merged_n)

        return n_players, n_nations, str(root)

    def _update_tour_classification_from_preview(self, season: str, tour_code: str, stage_key: str):
        """
        Aktualizuje plik klasyfikacji turnieju (TCS / FT / RAW AIR / itp.)
        na podstawie ostatnio wyświetlonej klasyfikacji:
        - Q1/Q2 → kwalifikacje
        - K1..K4 → konkurs.

        Plik docelowy:
            ./{season}/Klasyfikacje {season}/{season}_{tour_code}.csv

        Schemat kolumn:
        - TCS / FT / NT / RAWAIR-W / BB:
            LP.,JUMPER,NAT,K1,K2,K3,K4,Overall
        - WILLINGEN5 / PLANICA7:
            LP.,JUMPER,NAT,Q1,K1,K2,Overall
        - RAWAIR-M:
            LP.,JUMPER,NAT,Q1,K1,Q2,K2,Overall

        Q1/Q2 to kwalifikacje, K1..K4 to konkursy.
        Overall = suma wszystkich kolumn etapowych.
        """

        # --- walidacja wejścia ---
        season = str(season or "").strip()
        tour_code = str(tour_code or "").strip().upper()
        stage_key = str(stage_key or "").strip().upper()

        if not season:
            raise ValueError("Podaj sezon (np. S45) dla klasyfikacji turnieju.")
        if not tour_code:
            raise ValueError("Podaj kod turnieju (np. TCS, RAWAIR-M).")
        if stage_key not in {"Q1","Q2","K1","K2","K3","K4"}:
            raise ValueError("Sesja musi być jedną z: Q1, Q2, K1, K2, K3, K4.")

        # źródło:
        # - dla Q1/Q2: ostatnia klasyfikacja kwalifikacji
        # - dla K1..K4: ostatnia klasyfikacja konkursu
        if stage_key.startswith("Q"):
            d = getattr(self, "_last_qual_cls", None)
            _what = "kwalifikacji"
        else:
            d = getattr(self, "_last_final_cls", None)
            _what = "konkursu"
        if d is None or len(d) == 0:
            raise RuntimeError(f"Brak ostatniej klasyfikacji {_what}.\nUruchom najpierw {_what}, żeby mieć wyniki.")

        d = d.copy()
        # Normalizacja kolumn
        for c in ("Zawodnik", "Kraj"):
            if c not in d.columns:
                raise RuntimeError(f"Klasyfikacja końcowa nie zawiera kolumny: {c}")
        d["Zawodnik"] = d["Zawodnik"].astype(str)
        d["Kraj"] = d["Kraj"].astype(str).str.upper().str.strip()

        # Punkty etapu: NIE używamy punktów FIS, tylko punkty z konkursu/kwalifikacji
        if "Punkty" in d.columns:
            pts = pd.to_numeric(d["Punkty"], errors="coerce").fillna(0.0)
        elif "Punkty FIS" in d.columns:
            # awaryjnie, gdyby brakowało 'Punkty'
            pts = pd.to_numeric(d["Punkty FIS"], errors="coerce").fillna(0.0)
        else:
            # na wszelki wypadek skala z miejsca, żeby nie wywalić się na pustych danych
            scale = [100,80,60,50,45,40,36,32,29,26,24,22,20,18,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1]
            m = pd.to_numeric(d.get("Miejsce", None), errors="coerce")
            pts = m.map(lambda x: scale[int(x)-1] if pd.notna(x) and 1 <= int(x) <= len(scale) else 0)
            pts = pd.to_numeric(pts, errors="coerce").fillna(0.0)

        d = d.assign(__PTS__=pts)

        # --- schemat kolumn w zależności od turnieju ---
        tour_schema = {
            "TCS":       ["K1","K2","K3","K4"],
            "FT":        ["K1","K2","K3","K4"],
            "NT":        ["K1","K2","K3","K4"],
            "RAWAIR-W":  ["K1","K2","K3","K4"],
            "BB":        ["K1","K2","K3","K4"],
            "WILLINGEN5":["Q1","K1","K2"],
            "PLANICA7":  ["Q1","K1","K2"],
            "RAWAIR-M":  ["Q1","K1","Q2","K2"],
        }

        if tour_code not in tour_schema:
            raise ValueError(f"Nieznany turniej: {tour_code}")

        stage_cols = tour_schema[tour_code]
        if stage_key not in stage_cols:
            raise ValueError(f"Etap {stage_key} nie występuje w turnieju {tour_code}.")

        # --- wczytaj / przygotuj plik klasyfikacji turnieju ---
        root = Path(f"./{season}/Klasyfikacje {season}").resolve()
        root.mkdir(parents=True, exist_ok=True)
        tour_path = root / f"{season}_{tour_code}.csv"

        def _read_csv_loose(p: Path) -> pd.DataFrame:
            if not p.exists():
                return pd.DataFrame()
            for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
                try:
                    return pd.read_csv(p, sep=None, engine="python", encoding=enc)
                except Exception:
                    continue
            try:
                return pd.read_csv(p, sep=";", encoding="utf-8")
            except Exception:
                return pd.DataFrame()

        cur = _read_csv_loose(tour_path)
        cur_cols = [str(c).strip() for c in cur.columns] if not cur.empty else []
        if not cur_cols or "JUMPER" not in cur_cols or "NAT" not in cur_cols:
            # start od pustej tabeli turniejowej
            cur = pd.DataFrame(columns=["LP.","JUMPER","NAT"] + stage_cols + ["Overall"])
        else:
            cur = cur.copy()
            cur.columns = cur_cols
            # dopilnuj, żeby istniały wszystkie kolumny etapowe + Overall
            for c in stage_cols:
                if c not in cur.columns:
                    cur[c] = 0.0
            if "Overall" not in cur.columns:
                cur["Overall"] = 0.0
            if "LP." not in cur.columns:
                cur.insert(0, "LP.", range(1, len(cur) + 1))

        # spójna postać NAT
        cur["NAT"] = cur.get("NAT", "").astype(str).str.upper().str.strip()

        # dane z bieżącego konkursu/kwalifikacji
        add = d[["Zawodnik","Kraj","__PTS__"]].copy()
        add.rename(columns={"Zawodnik":"JUMPER","Kraj":"NAT","__PTS__":"__ADD__"}, inplace=True)
        add["NAT"] = add["NAT"].astype(str).str.upper().str.strip()

        merged = cur.merge(add, on=["JUMPER","NAT"], how="outer")
        merged["__ADD__"] = pd.to_numeric(merged["__ADD__"], errors="coerce").fillna(0.0)

        # ustaw/aktualizuj kolumnę danego etapu
        merged[stage_key] = pd.to_numeric(merged.get(stage_key, 0.0), errors="coerce").fillna(0.0)
        merged[stage_key] = merged["__ADD__"]

        merged.drop(columns=["__ADD__"], inplace=True)

        # przelicz Overall jako sumę kolumn etapowych
        for c in stage_cols:
            merged[c] = pd.to_numeric(merged.get(c, 0.0), errors="coerce").fillna(0.0)
        merged["Overall"] = merged[stage_cols].sum(axis=1)

        # usuwamy wiersze kompletnie puste (bez JUMPER/NAT i bez punktów)
        merged["JUMPER"] = merged.get("JUMPER", "").astype(str)
        merged["NAT"] = merged.get("NAT", "").astype(str)
        mask_keep = (
            merged["JUMPER"].str.strip().ne("") |
            merged["NAT"].str.strip().ne("") |
            (merged["Overall"] != 0)
        )
        merged = merged.loc[mask_keep].copy()

        # sortowanie: najpierw Overall malejąco, potem JUMPER/NAT
        merged = merged.sort_values(
            by=["Overall","JUMPER","NAT"],
            ascending=[False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)

        # przelicz LP. i ustaw kolejność kolumn
        if "LP." in merged.columns:
            merged.drop(columns=["LP."], inplace=True)
        merged.insert(0, "LP.", range(1, len(merged) + 1))

        ordered_cols = ["LP.","JUMPER","NAT"] + stage_cols + ["Overall"]
        # dołóż ewentualne inne kolumny na koniec, żeby nic nie zgubić
        tail = [c for c in merged.columns if c not in ordered_cols]
        merged = merged[ordered_cols + tail]

        # zapis
        merged.to_csv(tour_path, sep=";", encoding="utf-8-sig", index=False)
        return len(merged), str(tour_path)

    def _on_update_tour_clicked(self, season: str, tour_code: str, stage_key: str):
        
        try:
            n_rows, path = self._update_tour_classification_from_preview(season, tour_code, stage_key)
            messagebox.showinfo(
                "Klasyfikacja turnieju",
                f"Zaktualizowano klasyfikację {tour_code} ({stage_key}).\\n"
                f"Liczba zawodników: {n_rows}\\n"
                f"Plik: {path}"
            )
        except Exception as e:
            messagebox.showerror("Klasyfikacja turnieju – błąd", str(e))

    def _on_update_classif_clicked(self, season: str, cycle: str):
        try:
            if not season or not cycle:
                raise ValueError("Podaj Sezon (np. S45) i Cykl (np. WC-M).")

            # --- Potwierdzenie przed aktualizacją ---
            try:
                hs = int(self.var_hs.get())
            except Exception:
                hs = 0
            extra = "\n\n\u26a0\ufe0f Nie zapomnij o lotach!" if hs > 160 else ""
            if not messagebox.askyesno(
                "Potwierdzenie",
                f"Czy na pewno chcesz zaktualizowa\u0107 {cycle}?{extra}"
            ):
                return

            # --- Twój istniejący kod (bez zmian) ---
            n_players, n_nations, root = self._update_classifications_from_preview(season, cycle)

            is_ski_flying = cycle.strip().upper().startswith("SKI_FLYING")

            if is_ski_flying:
                messagebox.showinfo(
                    "Aktualizacja klasyfikacji",
                    f"Zaktualizowano:\n"
                    f"- zawodnicy: {n_players} wierszy\n"
                    f"- kraje:     brak (Ski Flying)\n\n"
                    f"Folder: {root}\n\n"
                    f"Statystyki kariery (SQLite): pominięto (Ski Flying)"
                )
            else:
                # --- aktualizacja statystyk kariery w SQLite ---
                raport = aktualizuj_najnowszy_wynik(
                    sezon=season,
                    typ_cyklu=cycle,
                    wyniki_folder="./wyniki",
                    db_path="manager_skokow.db",
                )
                nations_info = f"{n_nations} wierszy"
                rek_info = ""
                if raport.get("nowe_rekordy_skoczni", 0):
                    rek_info += f"\n- nowe rekordy skoczni: {raport['nowe_rekordy_skoczni']}"
                if raport.get("nowe_rekordy_swiata", 0):
                    rek_info += "\n- 🌍 NOWY REKORD ŚWIATA!"
                if raport.get("nowe_rekordy_krajowe", 0):
                    rek_info += f"\n- nowe rekordy krajowe: {raport['nowe_rekordy_krajowe']}"
                messagebox.showinfo(
                    "Aktualizacja klasyfikacji",
                    f"Zaktualizowano:\n"
                    f"- zawodnicy: {n_players} wierszy\n"
                    f"- kraje:     {nations_info}\n\n"
                    f"Folder: {root}\n\n"
                    f"Statystyki kariery (SQLite):\n"
                    f"- zaktualizowano: {raport['zaktualizowano']} zawodników\n"
                    f"- skocznia: {raport['skocznia']}"
                    + rek_info
                    + (f"\n- pominięci: {', '.join(raport['pominieci'])}" if raport["pominieci"] else "")
                )
        except Exception as e:
            messagebox.showerror("Błąd aktualizacji", str(e))

    def _on_update_records_only_clicked(self, season: str):
        try:
            from aktualizuj_klasyfikacje import aktualizuj_tylko_rekord
            raport = aktualizuj_tylko_rekord(
                wyniki_folder="./wyniki",
                db_path="manager_skokow.db",
                sezon=season,
            )
            rek_info = ""
            if raport.get("nowe_rekordy_skoczni", 0):
                rek_info += f"\n- nowe rekordy skoczni: {raport['nowe_rekordy_skoczni']}"
            if raport.get("nowe_rekordy_swiata", 0):
                rek_info += "\n- 🌍 NOWY REKORD ŚWIATA!"
            if raport.get("nowe_rekordy_krajowe", 0):
                rek_info += f"\n- nowe rekordy krajowe: {raport['nowe_rekordy_krajowe']}"
            messagebox.showinfo(
                "Rekordy życiowe",
                f"Zaktualizowano rekordy: {raport['zaktualizowano']} zawodników\n"
                f"Skocznia: {raport['skocznia']}"
                + rek_info
                + (f"\nPominięci: {', '.join(raport['pominieci'])}" if raport["pominieci"] else "")
            )
        except Exception as e:
            messagebox.showerror("Błąd aktualizacji rekordów", str(e))
       
    def _export_champs_results(self, mode: str):
        # 1. Pobranie sezonu
        season_val = getattr(self, "_champs_season_var", None)
        season_str = (season_val.get().strip() if season_val is not None else "S45") or "S45"

        # 2. Budowanie listy części nazwy
        # Jeśli mode == "QUAL", ignorujemy pole Typ (IND/TEAM) i wstawiamy "Q"
        comp_type = "Q" if mode == "QUAL" else self._champs_type_var.get()

        parts = [
            season_str,                   # Sezon zawsze na początku
            self._champs_name_var.get(),   # Nazwa mistrzostw
            self._champs_sex_var.get(),    # Płeć
            comp_type,                     # Q lub (IND/TEAM/puste)
            self._champs_hill_var.get()    # Skocznia
        ]
        
        # 3. Usuwamy puste elementy i łączymy podkreślnikiem
        clean_parts = [p for p in parts if p.strip()]
        code = "_".join(clean_parts).upper()

        # 4. Wybór źródła danych
        if mode == "QUAL":
            src = getattr(self, "_last_qual_cls", None)
            label = "kwalifikacji"
        elif self._champs_ko64_var.get():      # <-- NOWY WARUNEK
            src = getattr(self, "_last_ko64_cls", None)
            label = "KO64"
        else:
            src = getattr(self, "_last_final_cls", None)
            label = "konkursu"

        if src is None or not isinstance(src, pd.DataFrame) or src.empty:
            messagebox.showwarning("Mistrzostwa – zapis", f"Brak danych {label} w podglądzie.")
            return

        df = src.copy()
        try:
            if "Miejsce" in df.columns:
                df = df.sort_values("Miejsce")
        except Exception:
            pass

        # 5. Ścieżka i zapis
        root = Path(".") / season_str / f"Mistrzostwa {season_str}"
        
        try:
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"{code}.csv"
            df.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
            messagebox.showinfo("Mistrzostwa – zapis", f"Zapisano do:\n{path}")
        except Exception as e:
            messagebox.showerror("Mistrzostwa – błąd", str(e))

    # === Wybór-YOG: zakładka z podzakładkami YOG-MEN / YOG-WOMEN (wiek 14–18) ===

    def _build_wybor_uni_tab(self, container):
        # rozciąganie
        try:
            container.rowconfigure(0, weight=1)
            container.columnconfigure(0, weight=1)
        except Exception:
            pass

        nb = ttk.Notebook(container)
        nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self._wyborUNI_countries = getattr(self, "_wyborUNI_countries", {})
        self._wyborUNI_players   = getattr(self, "_wyborUNI_players", {})
        self._wyborUNI_counters  = getattr(self, "_wyborUNI_counters", {})

        def _make_one(sex: str):
            page = ttk.Frame(nb)
            nb.add(page, text=("UNI-MEN" if sex == "M" else "UNI-WOMEN"))

            for r in (0,1):
                page.rowconfigure(r, weight=(0 if r==0 else 1))
            page.columnconfigure(0, weight=1)

            top = ttk.Frame(page); top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
            ctr_wrap = ttk.Frame(top); ctr_wrap.pack(side="left")

            lbl_uni = ttk.Label(ctr_wrap, text="UNI: 0"); lbl_uni.pack(side="left", padx=(0,8))
            lbl_wc  = ttk.Label(ctr_wrap, text="WC: 0");  lbl_wc.pack(side="left", padx=(0,8))
            lbl_coc = ttk.Label(ctr_wrap, text="COC: 0"); lbl_coc.pack(side="left", padx=(0,8))
            lbl_fc  = ttk.Label(ctr_wrap, text="FC: 0");  lbl_fc.pack(side="left")

            self._wyborUNI_counters[sex] = {"uni": lbl_uni, "wc": lbl_wc, "coc": lbl_coc, "fc": lbl_fc}

            ttk.Button(top, text="Odśwież", command=lambda s=sex: self._refresh_wybor_uni(s))\
                .pack(side="left", padx=(10,0))

            body = ttk.Frame(page); body.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=1)
            body.rowconfigure(0, weight=1)

            left  = Labeled(body, "Kraj – UNI – WC – COC – FC"); left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
            right = Labeled(body, "Zawodnicy");                   right.grid(row=0, column=1, sticky="nsew", padx=(6,0))

            # LEWO: kraje z flagą + kolumny
            tbl_c = Table(left.body)
            tbl_c.pack(fill=tk.BOTH, expand=True)
            try:
                tbl_c.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
                if hasattr(tbl_c, "enable_sorting"):
                    tbl_c.enable_sorting(numeric_cols=("UNI","WC","COC","FC"))
            except Exception:
                pass
            
                    # === TOOLS nad prawą tabelą (Zaznacz + Przenieś) ===
            tools = ttk.Frame(top); tools.pack(side="right")

            def _select_in_players(comp_code: str):
                """Zaznacz wiersze w prawej tabeli, gdzie kolumna 'Zawody' == comp_code."""
                tv = getattr(tbl_p, "tv_main", getattr(tbl_p, "tree", None))
                if tv is None:
                    return
                # wyczyść zaznaczenie
                try:
                    tv.selection_set(())
                except Exception:
                    pass

                code = str(comp_code).upper().strip()

                # spróbuj po nazwie kolumny, a jak się nie uda — po indeksie
                try:
                    # jeżeli Treeview rozpoznaje kolumnę po nazwie:
                    for iid in tv.get_children(""):
                        try:
                            val = tv.set(iid, "Zawody")
                        except Exception:
                            val = None
                        if str(val).upper().strip() == code:
                            tv.selection_add(iid)
                except Exception:
                    # fallback: odnajdź indeks kolumny "Zawody"
                    cols = list(tv["columns"])
                    idx = cols.index("Zawody") if "Zawody" in cols else None
                    if idx is not None:
                        for iid in tv.get_children(""):
                            vals = tv.item(iid).get("values", [])
                            if idx < len(vals) and str(vals[idx]).upper().strip() == code:
                                tv.selection_add(iid)

                # przewiń do pierwszego zaznaczonego
                try:
                    sel = tv.selection()
                    if sel:
                        tv.see(sel[0])
                except Exception:
                    pass

            # przyciski zaznaczania
            for lab in ("UNI", "WC", "COC", "FC"):
                ttk.Button(
                    tools, text=f"Zaznacz {lab}",
                    command=lambda c=lab: _select_in_players(c)
                ).pack(side="left", padx=4)

            # przenieś zaznaczonych do Listy Startowej
            ttk.Button(
                tools,
                text="Przenieś zaznaczonych do Listy Startowej",
                command=lambda: self._add_players_to_startlist(
                    self._tree_selection_to_df(
                        getattr(tbl_p, "tv_main", getattr(tbl_p, "tree", None)),
                        name_col=getattr(tbl_p, "_name_col", "Zawodnik")
                    )
                )
            ).pack(side="left", padx=(10,0))

            # PRAWO: zawodnicy (Lp. zamrożone)
            tbl_p = FrozenFirstColTable(right.body, "Lp.")
            # UWAGA: FrozenFirstColTable nie ma set_showed_columns — kolejność da DF w _refresh_wybor_uni
            try:
                tbl_p.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
            except Exception:
                pass
            tbl_p.pack(fill=tk.BOTH, expand=True)

            self._wyborUNI_countries[sex] = tbl_c
            self._wyborUNI_players[sex]   = tbl_p

            self._refresh_wybor_uni(sex)

        _make_one("M")
        _make_one("W")

    def _refresh_wybor_uni(self, sex: str):
        

        # LEWA: policz UNI/WC/COC/FC
        try:
            dfc = self._compute_wybor_uni_quota(sex)
        except Exception:
            dfc = pd.DataFrame(columns=["Kraj","UNI","WC","COC","FC"])

        tbl_c = (getattr(self, "_wyborUNI_countries", {}) or {}).get(sex)
        if tbl_c is not None:
            for col in ("Kraj","UNI","WC","COC","FC"):
                if col not in dfc.columns:
                    dfc[col] = [] if col=="Kraj" else 0
            dfc = dfc[["Kraj","UNI","WC","COC","FC"]]

            # liczniki
            try:
                
                tot_uni = int(pd.to_numeric(dfc["UNI"], errors="coerce").fillna(0).sum())
                tot_wc  = int(pd.to_numeric(dfc["WC"],  errors="coerce").fillna(0).sum())
                tot_coc = int(pd.to_numeric(dfc["COC"], errors="coerce").fillna(0).sum())
                tot_fc  = int(pd.to_numeric(dfc["FC"],  errors="coerce").fillna(0).sum())
            except Exception:
                tot_uni = tot_wc = tot_coc = tot_fc = 0

            ctr = (getattr(self, "_wyborUNI_counters", {}) or {}).get(sex)
            if ctr:
                try:
                    ctr["uni"].configure(text=f"UNI: {tot_uni}")
                    ctr["wc"].configure(text=f"WC: {tot_wc}")
                    ctr["coc"].configure(text=f"COC: {tot_coc}")
                    ctr["fc"].configure(text=f"FC: {tot_fc}")
                except Exception:
                    pass

            tbl_c.set_dataframe(dfc)
            try: tbl_c.autosize_columns()
            except Exception: pass

        # PRAWO: lista zawodników (kolejność: UNI → WC → COC → FC)
        try:
            dfp = self._players_from_quotas_uni(sex, quotas_df=dfc)
        except Exception:
            dfp = pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        tbl_p = (getattr(self, "_wyborUNI_players", {}) or {}).get(sex)
        if tbl_p is not None:
            desired = [c for c in ["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"] if c in dfp.columns]
            tbl_p.set_dataframe(dfp[desired] if desired else dfp)
            try: tbl_p.autosize_columns()
            except Exception: pass

    def _build_wybor_yog_tab(self, container):
        # rozciąganie
        try:
            container.rowconfigure(0, weight=1)
            container.columnconfigure(0, weight=1)
        except Exception:
            pass

        nb = ttk.Notebook(container)
        nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self._wyborYOG_countries = getattr(self, "_wyborYOG_countries", {})
        self._wyborYOG_players   = getattr(self, "_wyborYOG_players", {})
        self._wyborYOG_counters  = getattr(self, "_wyborYOG_counters", {})

        def _make_one(sex: str):
            page = ttk.Frame(nb)
            nb.add(page, text=("YOG-MEN" if sex == "M" else "YOG-WOMEN"))

            for r in (0,1):
                page.rowconfigure(r, weight=(0 if r==0 else 1))
            page.columnconfigure(0, weight=1)

            top = ttk.Frame(page); top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
            ctr_wrap = ttk.Frame(top); ctr_wrap.pack(side="left")

            lbl_yog = ttk.Label(ctr_wrap, text="YOG: 0"); lbl_yog.pack(side="left", padx=(0,8))
            lbl_wc  = ttk.Label(ctr_wrap, text="WC: 0");  lbl_wc.pack(side="left", padx=(0,8))
            lbl_coc = ttk.Label(ctr_wrap, text="COC: 0"); lbl_coc.pack(side="left", padx=(0,8))
            lbl_fc  = ttk.Label(ctr_wrap, text="FC: 0");  lbl_fc.pack(side="left")

            self._wyborYOG_counters[sex] = {"yog": lbl_yog, "wc": lbl_wc, "coc": lbl_coc, "fc": lbl_fc}

            ttk.Button(top, text="Odśwież", command=lambda s=sex: self._refresh_wybor_yog(s))\
                .pack(side="left", padx=(10,0))

            body = ttk.Frame(page); body.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=1)
            body.rowconfigure(0, weight=1)

            left  = Labeled(body, "Kraj – YOG – WC – COC – FC"); left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
            right = Labeled(body, "Zawodnicy");                   right.grid(row=0, column=1, sticky="nsew", padx=(6,0))

            # LEWO: kraje z flagą + kolumny
            tbl_c = Table(left.body)
            tbl_c.pack(fill=tk.BOTH, expand=True)
            try:
                tbl_c.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
                if hasattr(tbl_c, "enable_sorting"):
                    tbl_c.enable_sorting(numeric_cols=("YOG","WC","COC","FC"))
            except Exception:
                pass
            
                    # === TOOLS nad prawą tabelą (Zaznacz + Przenieś) ===
            tools = ttk.Frame(top); tools.pack(side="right")

            def _select_in_players(comp_code: str):
                """Zaznacz wiersze w prawej tabeli, gdzie kolumna 'Zawody' == comp_code."""
                tv = getattr(tbl_p, "tv_main", getattr(tbl_p, "tree", None))
                if tv is None:
                    return
                # wyczyść zaznaczenie
                try:
                    tv.selection_set(())
                except Exception:
                    pass

                code = str(comp_code).upper().strip()

                # spróbuj po nazwie kolumny, a jak się nie uda — po indeksie
                try:
                    # jeżeli Treeview rozpoznaje kolumnę po nazwie:
                    for iid in tv.get_children(""):
                        try:
                            val = tv.set(iid, "Zawody")
                        except Exception:
                            val = None
                        if str(val).upper().strip() == code:
                            tv.selection_add(iid)
                except Exception:
                    # fallback: odnajdź indeks kolumny "Zawody"
                    cols = list(tv["columns"])
                    idx = cols.index("Zawody") if "Zawody" in cols else None
                    if idx is not None:
                        for iid in tv.get_children(""):
                            vals = tv.item(iid).get("values", [])
                            if idx < len(vals) and str(vals[idx]).upper().strip() == code:
                                tv.selection_add(iid)

                # przewiń do pierwszego zaznaczonego
                try:
                    sel = tv.selection()
                    if sel:
                        tv.see(sel[0])
                except Exception:
                    pass

            # przyciski zaznaczania
            for lab in ("YOG", "WC", "COC", "FC"):
                ttk.Button(
                    tools, text=f"Zaznacz {lab}",
                    command=lambda c=lab: _select_in_players(c)
                ).pack(side="left", padx=4)

            # przenieś zaznaczonych do Listy Startowej
            ttk.Button(
                tools,
                text="Przenieś zaznaczonych do Listy Startowej",
                command=lambda: self._add_players_to_startlist(
                    self._tree_selection_to_df(
                        getattr(tbl_p, "tv_main", getattr(tbl_p, "tree", None)),
                        name_col=getattr(tbl_p, "_name_col", "Zawodnik")
                    )
                )
            ).pack(side="left", padx=(10,0))

            # PRAWO: zawodnicy (Lp. zamrożone)
            tbl_p = FrozenFirstColTable(right.body, "Lp.")
            # UWAGA: FrozenFirstColTable nie ma set_showed_columns — kolejność da DF w _refresh_wybor_yog
            try:
                tbl_p.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
            except Exception:
                pass
            tbl_p.pack(fill=tk.BOTH, expand=True)

            self._wyborYOG_countries[sex] = tbl_c
            self._wyborYOG_players[sex]   = tbl_p

            self._refresh_wybor_yog(sex)

        _make_one("M")
        _make_one("W")

    def _refresh_wybor_yog(self, sex: str):
        

        # LEWA: policz YOG/WC/COC/FC
        try:
            dfc = self._compute_wybor_yog_quota(sex)
        except Exception:
            dfc = pd.DataFrame(columns=["Kraj","YOG","WC","COC","FC"])

        tbl_c = (getattr(self, "_wyborYOG_countries", {}) or {}).get(sex)
        if tbl_c is not None:
            for col in ("Kraj","YOG","WC","COC","FC"):
                if col not in dfc.columns:
                    dfc[col] = [] if col=="Kraj" else 0
            dfc = dfc[["Kraj","YOG","WC","COC","FC"]]

            # liczniki
            try:
                
                tot_yog = int(pd.to_numeric(dfc["YOG"], errors="coerce").fillna(0).sum())
                tot_wc  = int(pd.to_numeric(dfc["WC"],  errors="coerce").fillna(0).sum())
                tot_coc = int(pd.to_numeric(dfc["COC"], errors="coerce").fillna(0).sum())
                tot_fc  = int(pd.to_numeric(dfc["FC"],  errors="coerce").fillna(0).sum())
            except Exception:
                tot_yog = tot_wc = tot_coc = tot_fc = 0

            ctr = (getattr(self, "_wyborYOG_counters", {}) or {}).get(sex)
            if ctr:
                try:
                    ctr["yog"].configure(text=f"YOG: {tot_yog}")
                    ctr["wc"].configure(text=f"WC: {tot_wc}")
                    ctr["coc"].configure(text=f"COC: {tot_coc}")
                    ctr["fc"].configure(text=f"FC: {tot_fc}")
                except Exception:
                    pass

            tbl_c.set_dataframe(dfc)
            try: tbl_c.autosize_columns()
            except Exception: pass

        # PRAWO: lista zawodników (kolejność: YOG → WC → COC → FC)
        try:
            dfp = self._players_from_quotas_yog(sex, quotas_df=dfc)
        except Exception:
            dfp = pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        tbl_p = (getattr(self, "_wyborYOG_players", {}) or {}).get(sex)
        if tbl_p is not None:
            desired = [c for c in ["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"] if c in dfp.columns]
            tbl_p.set_dataframe(dfp[desired] if desired else dfp)
            setattr(tbl_p, "_last_df", dfp[desired] if desired else dfp)
            self._install_players_sort(tbl_p, comp_order=("YOG","WC","COC","FC"))
            try: tbl_p.autosize_columns()
            except Exception: pass

    def _refresh_wybor_coch_tab(self, sex: str):
        """Odświeża dane w nowej zakładce COCH."""
        dfc = self._compute_wybor_coch_quota(sex)
        if sex in self._wyborCOCH_countries:
            self._wyborCOCH_countries[sex].set_dataframe(dfc)
            
        dfp = self._players_from_quotas_coch(sex, quotas_df=dfc)
        if sex in self._wyborCOCH_players:
            self._wyborCOCH_players[sex].set_dataframe(dfp)

    def _build_wybor_lato_tab(self, container):
        # układ
        try:
            container.rowconfigure(0, weight=1)
            container.columnconfigure(0, weight=1)
        except Exception:
            pass

        nb = ttk.Notebook(container)
        nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self._wyborLATO_countries = {}
        self._wyborLATO_players   = {}
        self._wyborLATO_counters  = {}

        def _make_one(sex: str):
            page = ttk.Frame(nb)
            nb.add(page, text=("MEN-LATO" if sex=="M" else "WOMEN-LATO"))

            for r in (0,1):
                page.rowconfigure(r, weight=(0 if r==0 else 1))
            page.columnconfigure(0, weight=1)

            top = ttk.Frame(page); top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
            ctr_wrap = ttk.Frame(top); ctr_wrap.pack(side="left")

            lbl_gp   = ttk.Label(ctr_wrap, text="GP: 0");   lbl_gp.pack(side="left", padx=(0,8))
            lbl_scoc = ttk.Label(ctr_wrap, text="SCOC: 0"); lbl_scoc.pack(side="left", padx=(0,8))
            self._wyborLATO_counters[sex] = {"gp": lbl_gp, "scoc": lbl_scoc}

            ttk.Button(top, text="Odśwież", command=lambda s=sex: self._refresh_wybor_lato_safe(s)).pack(side="left", padx=(10,0))

            body = ttk.Frame(page); body.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=1)
            body.rowconfigure(0, weight=1)

            left  = Labeled(body, "Kraj – GP – SCOC"); left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
            right = Labeled(body, "Zawodnicy (wg kwot LATO)"); right.grid(row=0, column=1, sticky="nsew", padx=(6,0))

            # LEWO
            tbl_c = Table(left.body); tbl_c.pack(fill=tk.BOTH, expand=True)
            try:
                tbl_c.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
                if hasattr(tbl_c, "enable_sorting"):
                    tbl_c.enable_sorting(numeric_cols=("GP","SCOC"))
            except Exception:
                pass

            # Przyciski „Zaznacz” oraz przeniesienie
            tools = ttk.Frame(top); tools.pack(side="right")
            def _select_in_players(code: str):
                tv = getattr(tbl_p, "tv_main", getattr(tbl_p, "tree", None))
                if tv is None: return
                try: tv.selection_set(())
                except Exception: pass
                # wybór po kolumnie „Zawody”
                cols = list(tv["columns"])
                idx = cols.index("Zawody") if "Zawody" in cols else None
                if idx is not None:
                    for iid in tv.get_children(""):
                        vals = tv.item(iid).get("values", [])
                        if idx < len(vals) and str(vals[idx]).upper().strip() == code:
                            tv.selection_add(iid)
                try:
                    sel = tv.selection()
                    if sel: tv.see(sel[0])
                except Exception:
                    pass

            ttk.Button(tools, text="Zaznacz GP",   command=lambda: _select_in_players("GP")).pack(side="left", padx=4)
            ttk.Button(tools, text="Zaznacz SCOC", command=lambda: _select_in_players("SCOC")).pack(side="left", padx=4)
            ttk.Button(
                tools,
                text="Przenieś zaznaczonych do Listy Startowej",
                command=lambda: self._add_players_to_startlist(
                    self._tree_selection_to_df(
                        getattr(tbl_p, "tv_main", getattr(tbl_p, "tree", None)),
                        name_col=getattr(tbl_p, "_name_col", "Zawodnik")
                    )
                )
            ).pack(side="left", padx=(10,0))

            # PRAWO
            tbl_p = FrozenFirstColTable(right.body, "Lp.")
            try: tbl_p.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
            except Exception: pass
            tbl_p.pack(fill=tk.BOTH, expand=True)
            self._install_players_sort(tbl_p, comp_order=("GP","SCOC"))
            self._wyborLATO_countries[sex] = tbl_c
            self._wyborLATO_players[sex]   = tbl_p

            self._refresh_wybor_lato_safe(sex)

        _make_one("M")
        _make_one("W")

    def _refresh_wybor_lato(self, sex: str):
        
        # LEWO: kwoty
        try:
            dfc = self._compute_wybor_lato_quota(sex)
        except Exception:
            dfc = pd.DataFrame(columns=["Kraj","GP","SCOC"])

        tbl_c = (getattr(self, "_wyborLATO_countries", {}) or {}).get(sex)
        if tbl_c is not None:
            for col in ("Kraj","GP","SCOC"):
                if col not in dfc.columns:
                    dfc[col] = [] if col=="Kraj" else 0
            dfc = dfc[["Kraj","GP","SCOC"]]
            # liczniki
            try:
                tot_gp   = int(pd.to_numeric(dfc["GP"],   errors="coerce").fillna(0).sum())
                tot_scoc = int(pd.to_numeric(dfc["SCOC"], errors="coerce").fillna(0).sum())
            except Exception:
                tot_gp = tot_scoc = 0
            ctr = (getattr(self, "_wyborLATO_counters", {}) or {}).get(sex)
            if ctr:
                try:
                    ctr["gp"].configure(text=f"GP: {tot_gp}")
                    ctr["scoc"].configure(text=f"SCOC: {tot_scoc}")
                except Exception:
                    pass
            tbl_c.set_dataframe(dfc)
            try: tbl_c.autosize_columns()
            except Exception: pass

        # PRAWO: zawodnicy
        try:
            dfp = self._players_from_quotas_lato(sex, quotas_df=dfc)
        except Exception:
            
            dfp = pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","UM","Forma","Zawody"])

        tbl_p = (getattr(self, "_wyborLATO_players", {}) or {}).get(sex)
        if tbl_p is not None:
            # upewnij się, że 'Lp.' istnieje
            if "Lp." not in dfp.columns:
                dfp = dfp.copy()
                dfp.insert(0, "Lp.", range(1, len(dfp)+1))

            desired = [c for c in ["Lp.","Zawodnik","Kraj","UM","Forma","Zawody"] if c in dfp.columns]
            df_show = dfp[desired] if desired else dfp

            tbl_p.set_dataframe(df_show)
            setattr(tbl_p, "_last_df", df_show)
            try:
                self._install_players_sort(tbl_p, comp_order=("GP","SCOC"))
            except Exception:
                pass

            try: tbl_p.autosize_columns()
            except Exception: pass

    def _refresh_wybor_lato_safe(self, sex: str):
        try:
            self._refresh_wybor_lato(sex)
        except AttributeError:
            # fallback dla starszych instalacji, gdzie używasz ogólnej metody
            try:
                self._refresh_wybor_tab(sex)
            except Exception:
                pass
        except Exception:
            # nie zabijaj GUI przy innych wyjątkach
            pass

        try:
            if hasattr(self, "_refresh_rights_tab"):
                self._refresh_rights_tab()
        except Exception:
            pass
        self._refresh_wybor_lato(sex)

    # === Wybór-JWC: zakładka z podzakładkami JWC-MEN / JWC-WOMEN =================
    def _build_wybor_jwc_tab(self, container):
        # >>> lepsze rozciągnięcie w dół
        try:
            container.rowconfigure(0, weight=1)
            container.columnconfigure(0, weight=1)
        except Exception:
            pass

        nb = ttk.Notebook(container)
        # ważne: pełne wypełnienie + expand
        nb.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self._wyborJWC_countries = getattr(self, "_wyborJWC_countries", {})
        self._wyborJWC_players   = getattr(self, "_wyborJWC_players", {})
        self._wyborJWC_players_tbl = getattr(self, "_wyborJWC_players_tbl", {})

        def _make_one(sex: str):
            page = ttk.Frame(nb)
            nb.add(page, text=("JWC-MEN" if sex == "M" else "JWC-WOMEN"))

            # zapewnij rozciąganie strony
            for r in (0,1):
                page.rowconfigure(r, weight=(0 if r==0 else 1))
            page.columnconfigure(0, weight=1)
            # schowek na referencje do liczników
            self._wyborJWC_counters = getattr(self, "_wyborJWC_counters", {})

            top = ttk.Frame(page); top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
            # >>> TRZY LICZNIKI
            ctr_wrap = ttk.Frame(top); ctr_wrap.pack(side="left")
            lbl_jwc = ttk.Label(ctr_wrap, text="JWC: 0"); lbl_jwc.pack(side="left", padx=(0,8))
            lbl_wc  = ttk.Label(ctr_wrap, text="WC: 0");  lbl_wc.pack(side="left", padx=(0,8))
            lbl_coc = ttk.Label(ctr_wrap, text="COC: 0"); lbl_coc.pack(side="left", padx=(0,0))

            # zapisz referencje, żeby _refresh mógł aktualizować
            self._wyborJWC_counters[sex] = {"jwc": lbl_jwc, "wc": lbl_wc, "coc": lbl_coc}
            
            ttk.Button(top, text="Odśwież",
                    command=lambda s=sex: self._refresh_wybor_jwc(s)).pack(side="left", padx=(10,0))

            body = ttk.Frame(page); body.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
            body.columnconfigure(0, weight=1)
            body.columnconfigure(1, weight=1)
            body.rowconfigure(0, weight=1)

            left  = Labeled(body, "Kraj – JWC – WC – COC"); left.grid(row=0, column=0, sticky="nsew", padx=(0,6))
            right = Labeled(body, "Zawodnicy");             right.grid(row=0, column=1, sticky="nsew", padx=(6,0))

            # --- LEWA: kraje ---
            tbl_c = Table(left.body)
            tbl_c.pack(fill=tk.BOTH, expand=True)
            try: tbl_c.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
            except Exception: pass

            # --- PRAWA: zawodnicy (Lp. zamrożona) ---
            right_top = ttk.Frame(right.body)
            right_top.pack(fill=tk.X, pady=(0, 4))

            ttk.Button(right_top, text="Zaznacz JWC",
                    command=lambda s=sex: self._select_in_jwc_table(s, "JWC")
                    ).pack(side="left", padx=4)

            ttk.Button(right_top, text="Zaznacz WC",
                    command=lambda s=sex: self._select_in_jwc_table(s, "WC")
                    ).pack(side="left", padx=4)

            ttk.Button(right_top, text="Zaznacz COC",
                    command=lambda s=sex: self._select_in_jwc_table(s, "COC")
                    ).pack(side="left", padx=4)

            ttk.Button(right_top, text="Przenieś zaznaczonych do listy startowej",
                    command=lambda s=sex: self._move_selected_to_startlist(s)
                    ).pack(side="left", padx=12)

            # --- Tabela zawodników (Lp. zamrożona, flaga przy zawodniku) ---
            tbl_p = FrozenFirstColTable(right.body, "Lp.")
            tbl_p.pack(fill=tk.BOTH, expand=True)
            try:
                tbl_p.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
            except Exception:
                pass

            self._wyborJWC_countries[sex]   = tbl_c
            self._wyborJWC_players_tbl[sex] = tbl_p
            self._wyborJWC_players[sex]     = tbl_p  # żeby _refresh mógł tego użyć


            self._refresh_wybor_jwc(sex)

        _make_one("M")
        _make_one("W")

    def _refresh_wybor_jwc(self, sex: str):
        """Odświeża tabele JWC dla danego sex ('M'/'W')."""
        

        # --- LEWA: kraje i kwoty JWC/WC/COC (korzysta z Twojej logiki obliczeń) ---
        try:
            dfc = self._compute_wybor_jwc_quota(sex)  # już masz w projekcie
        except Exception:
            dfc = pd.DataFrame(columns=["Kraj","JWC","WC","COC"])

        tbl_c = (getattr(self, "_wyborJWC_countries", {}) or {}).get(sex)
        if tbl_c is not None:
            for col in ("Kraj","JWC","WC","COC"):
                if col not in dfc.columns:
                    dfc[col] = [] if col=="Kraj" else 0
            dfc = dfc[["Kraj","JWC","WC","COC"]]
            # --- liczniki: suma miejsc w JWC/WC/COC (po krajach) ---
            try:
                
                tot_jwc = int(pd.to_numeric(dfc["JWC"], errors="coerce").fillna(0).sum()) if "JWC" in dfc else 0
                tot_wc  = int(pd.to_numeric(dfc["WC"],  errors="coerce").fillna(0).sum()) if "WC"  in dfc else 0
                tot_coc = int(pd.to_numeric(dfc["COC"], errors="coerce").fillna(0).sum()) if "COC" in dfc else 0
            except Exception:
                tot_jwc = tot_wc = tot_coc = 0

            ctr = (getattr(self, "_wyborJWC_counters", {}) or {}).get(sex)
            if ctr:
                try:
                    ctr["jwc"].configure(text=f"JWC: {tot_jwc}")
                    ctr["wc"].configure(text=f"WC: {tot_wc}")
                    ctr["coc"].configure(text=f"COC: {tot_coc}")
                except Exception:
                    pass
            
            tbl_c.set_dataframe(dfc)
            try: tbl_c.autosize_columns()
            except Exception: pass

        # --- PRAWA: zawodnicy (wg JWC → WC → COC) ---
        try:
            dfp = self._players_from_quotas_jwc(sex, quotas_df=dfc)  # już masz w projekcie
        except Exception:
            dfp = pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        tbl_p = (getattr(self, "_wyborJWC_players", {}) or {}).get(sex)
        if tbl_p is not None:
            desired = [c for c in ["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"] if c in dfp.columns]
            tbl_p.set_dataframe(dfp[desired] if desired else dfp)
            try: tbl_p.autosize_columns()
            except Exception: pass
    # ============================================================================ 

    def _select_in_jwc_table(self, sex: str, comp_code: str):
        """Zaznacza wiersze w prawej tabeli JWC, gdzie kolumna 'Zawody' == comp_code."""
        tbl = (getattr(self, "_wyborJWC_players_tbl", {}) or {}).get(sex)
        if tbl is None:
            return
        tv = getattr(tbl, "tv_main", getattr(tbl, "tree", None))
        if tv is None:
            return

        selected = []
        for iid in tv.get_children(""):
            try:
                val = tv.set(iid, "Zawody")
            except Exception:
                continue
            if str(val).strip().upper() == comp_code.upper():
                selected.append(iid)

        if selected:
            try:
                tv.selection_set(selected)
                tv.see(selected[0])
            except Exception:
                pass

    def _move_selected_to_startlist(self, sex: str):
        """Przenosi zaznaczonych zawodników z JWC do listy startowej (MEN/WOMEN)."""
        tbl = (getattr(self, "_wyborJWC_players_tbl", {}) or {}).get(sex)
        if tbl is None:
            print("[JWC] Nie znaleziono tabeli zawodników.")
            return

        tv = getattr(tbl, "tv_main", getattr(tbl, "tree", None))
        if tv is None:
            print("[JWC] Nie znaleziono widoku Treeview.")
            return

        # sprawdź czy coś jest zaznaczone
        selected = tv.selection()
        if not selected:
            print("[JWC] Brak zaznaczonych zawodników do przeniesienia.")
            return

        try:
            # identyczna logika jak w Wybór-MEN/WOMEN
            df = self._tree_selection_to_df(
                tv,
                name_col=getattr(tbl, "_name_col", "Zawodnik")
            )
            self._add_players_to_startlist(df)
            print(f"[JWC] Przeniesiono {len(df)} zawodników ({sex}) do listy startowej.")
        except Exception as e:
            print(f"[JWC] Błąd podczas przenoszenia do listy startowej: {e}")

    def _reset_and_set_table(self, tree_attr: str, parent, df: pd.DataFrame, highlighter=None):
        """Usuwa starą tabelę i tworzy nową z podanym DataFrame’em (żeby nie wczytywała starych kolumn)."""
        old = getattr(self, tree_attr, None)
        try:
            if old is not None:
                old.destroy()
        except Exception as e:
            print(f"[WARN] Table reset: failed to destroy old widget: {e}")
        t = Table(parent)
        t.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        t.pack(fill=tk.BOTH, expand=True)
        setattr(self, tree_attr, t)
        t.highlighter = highlighter
        t.set_dataframe(df)

    def _compute_fixed_quota_df(self, sex: str):
        
        def _m(comp: str):
            d = self._compute_quota_map(f"{comp}-{sex}") or {}
            return {str(k).upper().strip(): int(v) for k, v in d.items()}

        wc  = _m("WC")
        coc = _m("COC")
        fc  = _m("FC")

        all_nats = sorted(set(wc) | set(coc) | set(fc))
        rows = [{"Kraj": nat,
                "WC":  wc.get(nat, 0),
                "COC": coc.get(nat, 0),
                "FC":  fc.get(nat, 0)} for nat in all_nats]

        df = pd.DataFrame(rows, columns=["Kraj", "WC", "COC", "FC"])
        df["Kraj"] = df["Kraj"].astype(str)
        for c in ("WC", "COC", "FC"):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        return df

    def _refresh_kwoty_tab(self, sex: str):
        
        try:
            dfc = self._compute_fixed_quota_df(sex)
        except Exception:
            dfc = pd.DataFrame(columns=["Kraj", "WC", "COC", "FC"])

        # Gwarancja kolumn nawet gdy DF pusty
        for col in ("Kraj", "WC", "COC", "FC"):
            if col not in dfc.columns:
                dfc[col] = [] if col == "Kraj" else 0
        dfc = dfc[["Kraj", "WC", "COC", "FC"]]

        for t in (self._kwoty_countries.get(sex, []) or []):
            try:
                t.set_dataframe(dfc)
                # pokaż dokładnie te kolumny, jeśli widżet to wspiera
                if hasattr(t, "set_showed_columns"):
                    t.set_showed_columns(["Kraj", "WC", "COC", "FC"])
                if hasattr(t, "autosize_columns"):
                    t.autosize_columns()
            except Exception:
                pass
        self._update_wybor_sums(sex, dfc)

    def _all_known_countries(self) -> set[str]:
        nats: set[str] = set()
        # 1) z katalogu flag
        flag_dir = getattr(self.tab_klasyfikacje, "flag_dir", FLAGS_DIR)
        try:
            for p in Path(flag_dir).glob("*.png"):
                code = p.stem.upper().strip()
                if code and code not in {"N/A", "BYE"}:
                    nats.add(code)
        except Exception:
            pass
        # 2) z „Klasyfikacje” (players/nations)
        try:
            sd = getattr(self.tab_klasyfikacje, "sheet_data", {}) or {}
            for _tag, data in sd.items():
                for key in ("players", "nations"):
                    df = (data or {}).get(key)
                    if df is None or df.empty:
                        continue
                    if "NAT" in df.columns:
                        nats |= set(df["NAT"].astype(str).str.upper())
        except Exception:
            pass
        # 3) z bazy zawodników
        try:
            df = getattr(self, "_roster_df_cache", None)
            if df is not None and not df.empty and "Kraj" in df.columns:
                nats |= set(df["Kraj"].astype(str).str.upper())
        except Exception:
            pass
        return {c for c in nats if c and c not in {"N/A", "BYE"}}

    def _aggregate_quotas_summary(self, sex: str):
        
        comps = ("WC","COC","FC")
        maps = {}
        for c in comps:
            try:
                maps[c] = self._compute_quota_map(f"{c}-{sex}") or {}
            except Exception:
                maps[c] = {}
        # >>> NOWE: dołóż kraje z bazy/klasyfikacji
        try:
            extra = set(self._all_known_countries())
        except Exception:
            extra = set()
        all_nats = sorted(set().union(*[set(m.keys()) for m in maps.values()]) | extra)

        rows = []
        for nat in all_nats:
            rows.append({
                "Kraj": nat,
                "WC":  int(maps["WC"].get(nat, 0)),
                "COC": int(maps["COC"].get(nat, 0)),
                "FC":  int(maps["FC"].get(nat, 0)),
            })
        return pd.DataFrame(rows)

    def _compute_wybor_ch_quota(self, sex: str):
        """
        Efektywne kwoty do Wybór-CH:
        - WC: min(Prawa Startów WC, 4)  [ignorujemy 'Kwoty WC']
        - COC/FC: jak dotąd, z odejmowaniem wykorzystanych WC/COC i przycięciem do kwot.
        Zwraca DF: Kraj | WC | COC | FC
        """

        def _norm(df):
            if df is None:
                df = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
            cols = [c for c in ["Kraj","WC","COC","FC"] if c in df.columns]
            if "Kraj" not in cols:
                df = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
            else:
                df = df[cols].copy()
            for c in ["WC","COC","FC"]:
                if c not in df.columns:
                    df[c] = 0
            df["Kraj"] = df["Kraj"].astype(str).str.upper().str.strip()
            for c in ["WC","COC","FC"]:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
            return df

        # 1) Kwoty z zakładki Kwoty Startowe (użyjemy dla COC/FC)
        try:
            kw = _norm(self._aggregate_quotas_summary(sex))
        except Exception:
            kw = _norm(None)

        # 2) Prawa Startów (to z nich bierzemy 'r_wc', 'r_coc', 'r_fc')
        rights_df = getattr(self, "_last_rights_df", {}).get(sex, None)
        if rights_df is None:
            try:
                rights_df = self._aggregate_rights_summary(sex)
            except Exception:
                rights_df = None
        pr = _norm(rights_df)

        # 3) Połącz
        all_countries = sorted(set(kw["Kraj"]).union(set(pr["Kraj"])))
        base = pd.DataFrame({"Kraj": all_countries})

        eff = base.merge(kw, on="Kraj", how="left").fillna(0)
        prn = pr.rename(columns={"WC":"WC_r","COC":"COC_r","FC":"FC_r"})
        eff = eff.merge(prn, on="Kraj", how="left").fillna(0)

        for c in ["WC","COC","FC","WC_r","COC_r","FC_r"]:
            eff[c] = pd.to_numeric(eff[c], errors="coerce").fillna(0).astype(int)

        kw_wc, kw_coc, kw_fc = eff["WC"], eff["COC"], eff["FC"]
        r_wc,  r_coc,  r_fc  = eff["WC_r"], eff["COC_r"], eff["FC_r"]

        # --- KLUCZOWA ZMIANA DLA CH: WC = min(Prawa Startów WC, 4) ---
        w_wc  = np.minimum(r_wc, 4)

        # COC/FC – jak dotąd, ale odejmujemy wykorzystane WC (i COC) oraz przycinamy do kwot z 'Kwoty Startowe'
        w_coc = np.minimum(kw_coc, np.maximum(0, r_coc - w_wc))
        w_fc  = np.minimum(kw_fc,  np.maximum(0, r_fc  - w_wc - w_coc))

        out = eff[["Kraj"]].copy()
        out["WC"]  = w_wc.astype(int)
        out["COC"] = w_coc.astype(int)
        out["FC"]  = w_fc.astype(int)
        return out

    def _compute_wybor_min_quota(self, sex: str):
        """
        Zwraca DataFrame [Kraj, WC, COC, FC] dla zakładek Wybór
        wg logiki:
        W_WC  = min(Kwoty_WC,  Prawa_WC)
        W_COC = min(Kwoty_COC, max(0, Prawa_COC - W_WC))
        W_FC  = min(Kwoty_FC,  max(0, Prawa_FC  - W_WC - W_COC))
        """
        
        

        def _norm(df):
            if df is None:
                df = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
            cols = [c for c in ["Kraj","WC","COC","FC"] if c in df.columns]
            if "Kraj" not in cols:
                df = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
            else:
                df = df[cols].copy()
            for c in ["WC","COC","FC"]:
                if c not in df.columns:
                    df[c] = 0
            df["Kraj"] = df["Kraj"].astype(str).str.upper().str.strip()
            for c in ["WC","COC","FC"]:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
            return df

        # 1) Kwoty z zakładki Kwoty Startowe
        try:
            kw = _norm(self._aggregate_quotas_summary(sex))
        except Exception:
            kw = _norm(None)

        # 2) Prawa Startów – z cache'u (albo z agregatora, jeśli masz)
        rights_df = getattr(self, "_last_rights_df", {}).get(sex, None)
        if rights_df is None:
            try:
                rights_df = self._aggregate_rights_summary(sex)  # jeśli istnieje
            except Exception:
                rights_df = None
        pr = _norm(rights_df)

        # 3) Połącz kraje i policz minimalizacje z odejmowaniem
        all_countries = sorted(set(kw["Kraj"]).union(set(pr["Kraj"])))
        base = pd.DataFrame({"Kraj": all_countries})

        eff = base.merge(kw, on="Kraj", how="left").fillna(0)
        prn = pr.rename(columns={"WC":"WC_r","COC":"COC_r","FC":"FC_r"})
        eff = eff.merge(prn, on="Kraj", how="left").fillna(0)

        for c in ["WC","COC","FC","WC_r","COC_r","FC_r"]:
            eff[c] = pd.to_numeric(eff[c], errors="coerce").fillna(0).astype(int)

        kw_wc, kw_coc, kw_fc = eff["WC"], eff["COC"], eff["FC"]
        r_wc,  r_coc,  r_fc  = eff["WC_r"], eff["COC_r"], eff["FC_r"]

        w_wc  = np.minimum(kw_wc, r_wc)
        w_coc = np.minimum(kw_coc, np.maximum(0, r_coc - w_wc))
        w_fc  = np.minimum(kw_fc,  np.maximum(0, r_fc  - w_wc - w_coc))

        out = eff[["Kraj"]].copy()
        out["WC"]  = w_wc.astype(int)
        out["COC"] = w_coc.astype(int)
        out["FC"]  = w_fc.astype(int)
        return out

    def _compute_wybor_jwc_quota(self, sex: str):
        """
        Zwraca DF: Kraj – JWC – WC – COC dla Wybór-JWC:
        • JWC: wiek ≤ 20, max 4/kraj, bez ograniczeń PS (top po ability)
        • r_wc  = max(0, Prawo_WC  - JWC_pwc)
        • r_coc = max(0, Prawo_COC - JWC_pcoc)
        • WC  = min(Kwota_WC, r_wc)
        • COC = min(Kwota_COC, max(r_coc - WC, 0))
        """

        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Kraj","JWC","WC","COC"])

        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]

        # ability
        um = pd.to_numeric(base.get("UM", 50), errors="coerce").fillna(50)
        fo = pd.to_numeric(base.get("Forma", 50), errors="coerce").fillna(50)
        base["__ability"] = 0.65*um + 0.35*fo

        # PRAWA STARTU → __PS (ZANIM wydzielimy <=20)
        ps = pd.to_numeric(base.get("PrawoStartu", 0), errors="coerce").fillna(0).astype(int)
        base["__PS"] = ps

        # wiek → ≤20 do JWC (nie tylko „juniorzy”)
        if "Wiek" in base.columns:
            age = pd.to_numeric(base["Wiek"], errors="coerce").fillna(0).astype(int)
        elif "Rok ur." in base.columns:
            age = (date.today().year - pd.to_numeric(base["Rok ur."], errors="coerce")).fillna(99).astype(int)
        else:
            age = pd.Series([99]*len(base), index=base.index, dtype=int)

        pool20 = base[age <= 20].copy()
        pool20["Kraj"] = pool20.get("Kraj","").astype(str).str.upper().str.strip()

        # top4 do JWC per kraj + liczenie JWC_pwc (PS 1–3) i JWC_pcoc (PS 1–6)
        jwc_cnt, jwc_pwc, jwc_pcoc = {}, {}, {}
        for nat, grp in pool20.groupby("Kraj"):
            top = grp.sort_values("__ability", ascending=False, kind="mergesort").head(4)
            jwc_cnt[nat] = int(len(top))
            # BEZPIECZNY odczyt PS (gdyby '__PS' nie istniało, użyj 'PrawoStartu' lub 0)
            top_ps = pd.to_numeric(top.get("__PS", top.get("PrawoStartu", 0)), errors="coerce").fillna(0).astype(int)
            jwc_pwc[nat]  = int(top_ps.isin({1,2,3}).sum())
            jwc_pcoc[nat] = int(top_ps.isin(set(range(1,7))).sum())

        # Kwoty: z zakładki „Kwoty Startowe”
        try:
            kw = self._compute_wybor_min_quota(sex)  # Kraj, WC, COC, FC (FC ignorujemy)
        except Exception:
            kw = pd.DataFrame(columns=["Kraj","WC","COC"])
        if "Kraj" not in kw.columns:
            kw["Kraj"] = []
        kw["Kraj"] = kw["Kraj"].astype(str).str.upper().str.strip()
        kw = kw[["Kraj","WC","COC"]].copy().fillna(0)

        # Prawa Startów: z zakładki „Prawa Startów”
        try:
            rights_all = getattr(self, "_last_rights_df", {}).get(sex, pd.DataFrame())
            pr = rights_all[["Kraj","WC","COC"]].copy()
        except Exception:
            pr = pd.DataFrame(columns=["Kraj","WC","COC"])
        for c in ("WC","COC"):
            pr[c] = pd.to_numeric(pr.get(c,0), errors="coerce").fillna(0).astype(int)
        pr["Kraj"] = pr.get("Kraj","").astype(str).str.upper().str.strip()

        eff = pd.DataFrame({"Kraj": sorted(set(kw["Kraj"]).union(set(pr["Kraj"])).union(set(jwc_cnt.keys())))})

        eff = eff.merge(kw, how="left", on="Kraj").fillna(0)
        eff = eff.merge(pr.rename(columns={"WC":"Prawo_WC","COC":"Prawo_COC"}), how="left", on="Kraj").fillna(0)

        # r_wc / r_coc po odjęciu tych, którzy poszli do JWC i mieli dane prawo
        eff["JWC"]      = eff["Kraj"].map(lambda k: int(jwc_cnt.get(k,0))).astype(int)
        eff["JWC_pwc"]  = eff["Kraj"].map(lambda k: int(jwc_pwc.get(k,0))).astype(int)
        eff["JWC_pcoc"] = eff["Kraj"].map(lambda k: int(jwc_pcoc.get(k,0))).astype(int)

        eff["r_wc"]  = np.maximum(0, pd.to_numeric(eff["Prawo_WC"],  errors="coerce").fillna(0).astype(int) -
                                    pd.to_numeric(eff["JWC_pwc"],   errors="coerce").fillna(0).astype(int)).astype(int)
        eff["r_coc"] = np.maximum(0, pd.to_numeric(eff["Prawo_COC"], errors="coerce").fillna(0).astype(int) -
                                    pd.to_numeric(eff["JWC_pcoc"],  errors="coerce").fillna(0).astype(int)).astype(int)

        kw_wc  = pd.to_numeric(eff["WC"],  errors="coerce").fillna(0).astype(int)
        kw_coc = pd.to_numeric(eff["COC"], errors="coerce").fillna(0).astype(int)

        eff["WC_eff"]  = np.minimum(kw_wc,  eff["r_wc"]).astype(int)
        eff["COC_eff"] = np.minimum(kw_coc, np.maximum(0, eff["r_coc"] - eff["WC_eff"])).astype(int)

        out = eff[["Kraj","JWC"]].copy()
        out["WC"]  = eff["WC_eff"].astype(int)
        out["COC"] = eff["COC_eff"].astype(int)

        # Jeśli kraj nie ma żadnego zawodnika ≤20, JWC = 0 (żeby prawa lista nie była pusta „mimo JWC>0”)
        real_has20 = set(pool20["Kraj"].unique())
        out.loc[~out["Kraj"].isin(real_has20), "JWC"] = 0

        return out.sort_values("Kraj").reset_index(drop=True)

    def _compute_wybor_uni_quota(self, sex: str):
        """
        Zwraca DF: Kraj – UNI – WC – COC – FC dla Wybór-UNI.
        • UNI: wiek 18–25, max 4/kraj (bez ograniczeń PS) — top ability.
        • r_wc  = max(0, Prawo_WC  - UNI_pwc)
        • r_coc = max(0, Prawo_COC - UNI_pcoc)
        • r_fc  = max(0, Prawo_FC  - UNI_pfc)
        • WC  = min(Kwota_WC, r_wc)
        • COC = min(Kwota_COC, max(r_coc - WC, 0))
        • FC  = min(Kwota_FC,  max(r_fc  - WC - COC, 0))
        """

        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Kraj","UNI","WC","COC","FC"])

        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]

        um = pd.to_numeric(base.get("UM", 50), errors="coerce").fillna(50)
        fo = pd.to_numeric(base.get("Forma", 50), errors="coerce").fillna(50)
        base["__ability"] = 0.65*um + 0.35*fo
        base["Kraj"] = base.get("Kraj","").astype(str).str.upper().str.strip()

        ps = pd.to_numeric(base.get("PrawoStartu", 0), errors="coerce").fillna(0).astype(int)
        base["__PS"] = ps

        # wiek → ≤20 do UNI (analogicznie do JWC)
        if "Wiek" in base.columns:
            age = pd.to_numeric(base["Wiek"], errors="coerce").fillna(0).astype(int)
        elif "Rok ur." in base.columns:
            age = (date.today().year - pd.to_numeric(base["Rok ur."], errors="coerce")).fillna(99).astype(int)
        else:
            age = pd.Series([99]*len(base), index=base.index, dtype=int)

        pool_uni = base[(age >= 18) & (age <= 25)].copy()

        # top4 do UNI per kraj + liczenie ile z nich miało prawa WC/COC/FC wg PS:
        # • WC: PS ∈ {1,2,3}
        # • COC: PS ∈ {1..6}
        # • FC: PS ∈ {1..7}   (analogicznie: „FC działa tak jak WC i COC” – obejmuje szerszy zakres)
        uni_cnt, uni_pwc, uni_pcoc, uni_pfc = {}, {}, {}, {}
        for nat, grp in pool_uni.groupby("Kraj"):
            top = grp.sort_values("__ability", ascending=False, kind="mergesort").head(4)
            uni_cnt[nat]  = int(len(top))
            top_ps = pd.to_numeric(top.get("__PS", top.get("PrawoStartu", 0)), errors="coerce").fillna(0).astype(int)
            uni_pwc[nat]  = int(top_ps.isin({1,2,3}).sum())
            uni_pcoc[nat] = int(top_ps.isin(set(range(1,7))).sum())
            uni_pfc[nat]  = int(top_ps.isin(set(range(1,8))).sum())

        # Kwoty minimalne (Twoja funkcja, zawiera WC/COC/FC)
        try:
            kw = self._compute_wybor_min_quota(sex)   # -> kolumny co najmniej: Kraj, WC, COC, FC
        except Exception:
            kw = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
        if "Kraj" not in kw.columns:
            kw["Kraj"] = []
        kw["Kraj"] = kw["Kraj"].astype(str).str.upper().str.strip()
        kw = kw[["Kraj","WC","COC","FC"]].copy().fillna(0)

        # Prawa startów (z cache’u Prawa Startów)
        try:
            rights_all = getattr(self, "_last_rights_df", {}).get(sex, pd.DataFrame())
            pr = rights_all[["Kraj","WC","COC","FC"]].copy()
        except Exception:
            pr = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
        for c in ("WC","COC","FC"):
            pr[c] = pd.to_numeric(pr.get(c,0), errors="coerce").fillna(0).astype(int)
        pr["Kraj"] = pr.get("Kraj","").astype(str).str.upper().str.strip()

        eff = pd.DataFrame({"Kraj": sorted(set(kw["Kraj"]).union(set(pr["Kraj"])).union(set(uni_cnt.keys())))})

        eff = eff.merge(kw, how="left", on="Kraj").fillna(0)
        eff = eff.merge(pr.rename(columns={"WC":"Prawo_WC","COC":"Prawo_COC","FC":"Prawo_FC"}), how="left", on="Kraj").fillna(0)

        eff["UNI"]      = eff["Kraj"].map(lambda k: int(uni_cnt.get(k,0))).astype(int)
        eff["UNI_pwc"]  = eff["Kraj"].map(lambda k: int(uni_pwc.get(k,0))).astype(int)
        eff["UNI_pcoc"] = eff["Kraj"].map(lambda k: int(uni_pcoc.get(k,0))).astype(int)
        eff["UNI_pfc"]  = eff["Kraj"].map(lambda k: int(uni_pfc.get(k,0))).astype(int)

        # resztowe prawa po zabraniu tych, którzy poszli do UNI i mieli dane prawo
        eff["r_wc"]  = np.maximum(0, pd.to_numeric(eff["Prawo_WC"],  errors="coerce").fillna(0).astype(int) - eff["UNI_pwc"]).astype(int)
        eff["r_coc"] = np.maximum(0, pd.to_numeric(eff["Prawo_COC"], errors="coerce").fillna(0).astype(int) - eff["UNI_pcoc"]).astype(int)
        eff["r_fc"]  = np.maximum(0, pd.to_numeric(eff["Prawo_FC"],  errors="coerce").fillna(0).astype(int) - eff["UNI_pfc"]).astype(int)

        kw_wc  = pd.to_numeric(eff["WC"],  errors="coerce").fillna(0).astype(int)
        kw_coc = pd.to_numeric(eff["COC"], errors="coerce").fillna(0).astype(int)
        kw_fc  = pd.to_numeric(eff["FC"],  errors="coerce").fillna(0).astype(int)

        eff["WC_eff"]  = np.minimum(kw_wc,  eff["r_wc"]).astype(int)
        eff["COC_eff"] = np.minimum(kw_coc, np.maximum(0, eff["r_coc"] - eff["WC_eff"])).astype(int)
        eff["FC_eff"]  = np.minimum(kw_fc,  np.maximum(0, eff["r_fc"]  - eff["WC_eff"] - eff["COC_eff"])).astype(int)

        out = eff[["Kraj","UNI"]].copy()
        out["WC"]  = eff["WC_eff"].astype(int)
        out["COC"] = eff["COC_eff"].astype(int)
        out["FC"]  = eff["FC_eff"].astype(int)

        # Jeśli kraj realnie nie ma zawodnika ≤20, UNI = 0 (jak w JWC)
        real_has_uni = set(pool_uni["Kraj"].unique())
        out.loc[~out["Kraj"].isin(real_has_uni), "UNI"] = 0

        return out.sort_values("Kraj").reset_index(drop=True)

    def _compute_wybor_yog_quota(self, sex: str):
        """
        Zwraca DF: Kraj – YOG – WC – COC – FC dla Wybór-YOG.
        • YOG: wiek 18–25, max 4/kraj (bez ograniczeń PS) — top ability.
        • r_wc  = max(0, Prawo_WC  - YOG_pwc)
        • r_coc = max(0, Prawo_COC - YOG_pcoc)
        • r_fc  = max(0, Prawo_FC  - YOG_pfc)
        • WC  = min(Kwota_WC, r_wc)
        • COC = min(Kwota_COC, max(r_coc - WC, 0))
        • FC  = min(Kwota_FC,  max(r_fc  - WC - COC, 0))
        """

        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Kraj","YOG","WC","COC","FC"])

        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]

        um = pd.to_numeric(base.get("UM", 50), errors="coerce").fillna(50)
        fo = pd.to_numeric(base.get("Forma", 50), errors="coerce").fillna(50)
        base["__ability"] = 0.65*um + 0.35*fo
        base["Kraj"] = base.get("Kraj","").astype(str).str.upper().str.strip()

        ps = pd.to_numeric(base.get("PrawoStartu", 0), errors="coerce").fillna(0).astype(int)
        base["__PS"] = ps

        # wiek → ≤20 do YOG (analogicznie do JWC)
        if "Wiek" in base.columns:
            age = pd.to_numeric(base["Wiek"], errors="coerce").fillna(0).astype(int)
        elif "Rok ur." in base.columns:
            age = (date.today().year - pd.to_numeric(base["Rok ur."], errors="coerce")).fillna(99).astype(int)
        else:
            age = pd.Series([99]*len(base), index=base.index, dtype=int)

        pool_yog = base[(age >= 14) & (age <= 18)].copy()

        # top4 do YOG per kraj + liczenie ile z nich miało prawa WC/COC/FC wg PS:
        # • WC: PS ∈ {1,2,3}
        # • COC: PS ∈ {1..6}
        # • FC: PS ∈ {1..7}   (analogicznie: „FC działa tak jak WC i COC” – obejmuje szerszy zakres)
        yog_cnt, yog_pwc, yog_pcoc, yog_pfc = {}, {}, {}, {}
        for nat, grp in pool_yog.groupby("Kraj"):
            top = grp.sort_values("__ability", ascending=False, kind="mergesort").head(4)
            yog_cnt[nat]  = int(len(top))
            top_ps = pd.to_numeric(top.get("__PS", top.get("PrawoStartu", 0)), errors="coerce").fillna(0).astype(int)
            yog_pwc[nat]  = int(top_ps.isin({1,2,3}).sum())
            yog_pcoc[nat] = int(top_ps.isin(set(range(1,7))).sum())
            yog_pfc[nat]  = int(top_ps.isin(set(range(1,8))).sum())

        # Kwoty minimalne (Twoja funkcja, zawiera WC/COC/FC)
        try:
            kw = self._compute_wybor_min_quota(sex)   # -> kolumny co najmniej: Kraj, WC, COC, FC
        except Exception:
            kw = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
        if "Kraj" not in kw.columns:
            kw["Kraj"] = []
        kw["Kraj"] = kw["Kraj"].astype(str).str.upper().str.strip()
        kw = kw[["Kraj","WC","COC","FC"]].copy().fillna(0)

        # Prawa startów (z cache’u Prawa Startów)
        try:
            rights_all = getattr(self, "_last_rights_df", {}).get(sex, pd.DataFrame())
            pr = rights_all[["Kraj","WC","COC","FC"]].copy()
        except Exception:
            pr = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
        for c in ("WC","COC","FC"):
            pr[c] = pd.to_numeric(pr.get(c,0), errors="coerce").fillna(0).astype(int)
        pr["Kraj"] = pr.get("Kraj","").astype(str).str.upper().str.strip()

        eff = pd.DataFrame({"Kraj": sorted(set(kw["Kraj"]).union(set(pr["Kraj"])).union(set(yog_cnt.keys())))})

        eff = eff.merge(kw, how="left", on="Kraj").fillna(0)
        eff = eff.merge(pr.rename(columns={"WC":"Prawo_WC","COC":"Prawo_COC","FC":"Prawo_FC"}), how="left", on="Kraj").fillna(0)

        eff["YOG"]      = eff["Kraj"].map(lambda k: int(yog_cnt.get(k,0))).astype(int)
        eff["YOG_pwc"]  = eff["Kraj"].map(lambda k: int(yog_pwc.get(k,0))).astype(int)
        eff["YOG_pcoc"] = eff["Kraj"].map(lambda k: int(yog_pcoc.get(k,0))).astype(int)
        eff["YOG_pfc"]  = eff["Kraj"].map(lambda k: int(yog_pfc.get(k,0))).astype(int)

        # resztowe prawa po zabraniu tych, którzy poszli do YOG i mieli dane prawo
        eff["r_wc"]  = np.maximum(0, pd.to_numeric(eff["Prawo_WC"],  errors="coerce").fillna(0).astype(int) - eff["YOG_pwc"]).astype(int)
        eff["r_coc"] = np.maximum(0, pd.to_numeric(eff["Prawo_COC"], errors="coerce").fillna(0).astype(int) - eff["YOG_pcoc"]).astype(int)
        eff["r_fc"]  = np.maximum(0, pd.to_numeric(eff["Prawo_FC"],  errors="coerce").fillna(0).astype(int) - eff["YOG_pfc"]).astype(int)

        kw_wc  = pd.to_numeric(eff["WC"],  errors="coerce").fillna(0).astype(int)
        kw_coc = pd.to_numeric(eff["COC"], errors="coerce").fillna(0).astype(int)
        kw_fc  = pd.to_numeric(eff["FC"],  errors="coerce").fillna(0).astype(int)

        eff["WC_eff"]  = np.minimum(kw_wc,  eff["r_wc"]).astype(int)
        eff["COC_eff"] = np.minimum(kw_coc, np.maximum(0, eff["r_coc"] - eff["WC_eff"])).astype(int)
        eff["FC_eff"]  = np.minimum(kw_fc,  np.maximum(0, eff["r_fc"]  - eff["WC_eff"] - eff["COC_eff"])).astype(int)

        out = eff[["Kraj","YOG"]].copy()
        out["WC"]  = eff["WC_eff"].astype(int)
        out["COC"] = eff["COC_eff"].astype(int)
        out["FC"]  = eff["FC_eff"].astype(int)

        # Jeśli kraj realnie nie ma zawodnika ≤20, YOG = 0 (jak w JWC)
        real_has_yog = set(pool_yog["Kraj"].unique())
        out.loc[~out["Kraj"].isin(real_has_yog), "YOG"] = 0

        return out.sort_values("Kraj").reset_index(drop=True)

    def _compute_wybor_coch_quota(self, sex: str):
        """Zwraca DF ze skrótami kontynentów i sztywnym limitem 4."""
        
        cont_map = self._get_continents_map()
        all_nats = sorted(self._all_known_countries())
        
        # Mapa pełna nazwa -> skrót
        mapping = {
            "Europe": "EU", "Asia": "AS", "North America": "NA",
            "South America": "SA", "Africa": "AF", "Oceania": "OC"
        }
        
        cols = ["Kraj", "EU", "AS", "NA", "SA", "AF", "OC"]
        rows = []
        
        for nat in all_nats:
            continent_full = cont_map.get(nat, "Europe")
            short = mapping.get(continent_full, "EU")
            row = {c: 0 for c in cols}
            row["Kraj"] = nat
            if short in row:
                row[short] = 4
            rows.append(row)
            
        return pd.DataFrame(rows)

    def _get_continents_map(self):
        """Wczytuje plik ALL_NATIONS_CONTINENTS.csv z obsługą różnych kodowań."""
        
        path = "ALL_NATIONS_CONTINENTS.csv"
        
        if not os.path.exists(path):
            print(f"Błąd: Plik {path} nie istnieje w folderze programu.")
            return {}

        # Próbujemy najpierw utf-8-sig (z obsługą BOM), potem cp1250 (standard Windows w PL)
        for encoding in ["utf-8-sig", "cp1250", "latin-1"]:
            try:
                df = pd.read_csv(path, sep=";", encoding=encoding)
                # Sprawdzenie czy kolumny istnieją
                if "Kraj" in df.columns and "Continent" in df.columns:
                    # Zamieniamy na słownik: NAT -> Continent
                    return dict(zip(df["Kraj"].astype(str).str.upper().str.strip(), 
                                    df["Continent"].astype(str).str.strip()))
            except (UnicodeDecodeError, Exception):
                continue
        
        print("Nie udało się rozpoznać kodowania pliku CSV.")
        return {}
    
    def _players_from_quotas_coch(self, sex: str, quotas_df=None):
        """Buduje listę zawodników. Zawody = Pełna nazwa kontynentu, brak kolumny ability."""
        
        

        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Lp.", "Zawodnik", "Kraj", "Zawody", "UM", "Forma"])

        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]
        if "Kontuzja" in base.columns:
            base = base[pd.to_numeric(base["Kontuzja"], errors="coerce").fillna(0) == 0]
        
        # Ability tylko do sortowania wewnątrz funkcji
        base["__ability"] = 0.65 * pd.to_numeric(base["UM"], errors="coerce").fillna(50) + \
                            0.35 * pd.to_numeric(base["Forma"], errors="coerce").fillna(50)
        
        cont_map = self._get_continents_map()
        out_rows = []
        
        for nat, grp in base.groupby("Kraj"):
            continent = cont_map.get(nat, "Europe") # Tu wpisujemy samą nazwę kontynentu
            top4 = grp.sort_values("__ability", ascending=False).head(4)
            for _, r in top4.iterrows():
                out_rows.append({
                    "Zawodnik": r["Zawodnik"],
                    "Kraj": nat,
                    "Zawody": continent,
                    "UM": r["UM"],
                    "Forma": r["Forma"],
                    "ability": r["__ability"]
                })
        
        res = pd.DataFrame(out_rows)
        if res.empty: return res
        
        res = res.sort_values(["Zawody", "Kraj", "ability"], ascending=[True, True, False]).reset_index(drop=True)
        res.insert(0, "Lp.", np.arange(1, len(res) + 1))
        # Usuwamy ability przed wyświetleniem
        return res.drop(columns=["ability"])
    
# --- helper: bezpieczny odczyt praw z zakładki "Prawa Startów" ---
    def _rights_from_tab_rights(self, key: str) -> dict[str, int]:
        """
        Czyta prawa startów z zakładki 'Prawa Startów' z self.tab_rights._quota_tables.
        Obsługuje aliasy nazw i wymusza rebuild zakładki, jeśli cache jest puste.
        Zwraca dict {NAT: int}.
        """
        

        def _normalize_map(obj) -> dict[str, int]:
            m = {}
            if isinstance(obj, dict):
                it = obj.items()
            elif hasattr(obj, "to_dict"):
                try:
                    df = obj.copy()
                    cols = [str(c) for c in df.columns]
                    nat_col = next((c for c in cols if c.upper() in ("NAT","KRAJ","KOD","CODE")), None)
                    val_col = next((c for c in cols if c.lower().startswith("ilo") or c.upper() in ("Q","QUOTA","VAL","VALUE","AMOUNT")), None)
                    if not nat_col or not val_col:
                        return {}
                    it = zip(df[nat_col], df[val_col])
                except Exception:
                    it = []
            else:
                it = []
            for k, v in it:
                nat = str(k).strip().upper()
                try:
                    iv = int(pd.to_numeric(v, errors="coerce"))
                except Exception:
                    try:
                        iv = int(float(v))
                    except Exception:
                        iv = 0
                if nat:
                    m[nat] = max(0, iv)
            return m

        tab = getattr(self, "tab_rights", None)
        if not tab:
            return {}

        def _grab(qt: dict) -> dict[str,int]:
            aliases = {
                key,
                key.replace("-", " "),
                key.replace("-", "_"),
                key.replace("-M"," M").replace("-W"," W"),
                key.replace("-M"," MEN").replace("-W"," WOMEN"),
                key.upper(), key.lower(),
            }
            acc = {}
            for k in aliases:
                src = (qt or {}).get(k)
                acc.update(_normalize_map(src))
            return acc

        # 1) spróbuj z cache
        qt = getattr(tab, "_quota_tables", {}) or {}
        got = _grab(qt)
        if got:
            return got

        # 2) cache puste → spróbuj wymusić rebuild zakładki
        for meth in ("rebuild_all","refresh_all","reload_all","_rebuild_all","_refresh_all","_reload_all"):
            fn = getattr(tab, meth, None)
            try:
                if callable(fn):
                    fn()
            except Exception:
                pass

        qt = getattr(tab, "_quota_tables", {}) or {}
        return _grab(qt)

    def _compute_wybor_lato_quota(self, sex: str):
        
        sex = (sex or "M").upper()[:1]

        q_gp   = dict(self._compute_quota_map(f"GP-{sex}")   or {})
        q_scoc = dict(self._compute_quota_map(f"SCOC-{sex}") or {})

        r_coc = self._rights_from_tab_rights(f"COC-{sex}")
        r_fc  = self._rights_from_tab_rights(f"FC-{sex}")

        # --- NOWE: fallback, jeśli r_coc/r_fc puste, użyj ostatnich praw z _last_rights_df ---
        if (not r_coc or not r_fc) and hasattr(self, "_last_rights_df"):
            try:
                df_last = (self._last_rights_df or {}).get(sex)
                if df_last is not None and not df_last.empty:
                    # słowniki {NAT: liczba}
                    rc = df_last.set_index("Kraj")["COC"].to_dict() if "COC" in df_last.columns else {}
                    rf = df_last.set_index("Kraj")["FC"].to_dict()  if "FC"  in df_last.columns else {}
                    if not r_coc: r_coc = rc
                    if not r_fc:  r_fc  = rf
            except Exception:
                pass
        # --- KONIEC fallbacku ---

        nations = sorted(set(q_gp) | set(q_scoc) | set(r_coc) | set(r_fc))
        rows = []
        for nat in nations:
            kw_gp   = int(q_gp.get(nat, 0))
            kw_scoc = int(q_scoc.get(nat, 0))
            pr_coc  = int(r_coc.get(nat, 0))
            pr_fc   = int(r_fc.get(nat, 0))

            gp_final   = min(kw_gp, pr_coc)
            scoc_final = min(kw_scoc, max(pr_fc - gp_final, 0))
            rows.append({"Kraj": nat, "GP": gp_final, "SCOC": scoc_final})

        df = pd.DataFrame(rows, columns=["Kraj","GP","SCOC"]).sort_values("Kraj", kind="mergesort").reset_index(drop=True)
        return df

    # === WYBÓR-LATO: lista zawodników z podziałem GP/SCOC ===
    def _players_from_quotas_lato(self, sex: str, quotas_df):
        df = getattr(self, "_roster_df_cache", pd.DataFrame()).copy()
        if df.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Zawody","UM","Forma","ability"])

        sex_ser = df.get("Sex", df.get("Płeć", ""))
        df = df[sex_ser.astype(str).str.upper().str[0].eq(sex)]
        if "Kontuzja" in df.columns:
            k = pd.to_numeric(df["Kontuzja"], errors="coerce").fillna(0).astype(int)
            df = df[k.eq(0)]
        df["UM"] = pd.to_numeric(df.get("UM",0), errors="coerce").fillna(0.0)
        df["Forma"] = pd.to_numeric(df.get("Forma",0), errors="coerce").fillna(0.0)
        df["ability"] = 0.65*df["UM"] + 0.35*df["Forma"]

        # PrawoStartu: GP wymaga 1–6, SCOC wymaga 1–7
        ps = pd.to_numeric(df.get("PrawoStartu", 0), errors="coerce").fillna(0).astype(int)
        df["__PS"] = ps
        GP_PS   = set(range(1, 7))   # 1–6
        SCOC_PS = set(range(1, 8))   # 1–7
        PS_ALLOWED = {"GP": GP_PS, "SCOC": SCOC_PS}

        used, rows = set(), []
        def pick(cycle_col, label):
            nonlocal used, rows
            allowed_ps = PS_ALLOWED.get(label, set(range(1, 8)))
            for _, r in quotas_df.iterrows():
                nat = str(r["Kraj"]).strip().upper()
                need = int(r[cycle_col])
                if need <= 0:
                    continue
                cand = df.assign(_K=df.get("Kraj","").astype(str).str.strip().str.upper())
                cand = cand[cand["_K"].eq(nat)].sort_values("ability", ascending=False, kind="mergesort")
                cand = cand[~cand["Zawodnik"].isin(used)]
                cand = cand[cand["__PS"].isin(allowed_ps)]
                for __, rr in cand.head(need).iterrows():
                    rows.append({"Zawodnik": rr.get("Zawodnik",""), "Kraj": nat, "Zawody": label,
                                "UM": rr.get("UM",0), "Forma": rr.get("Forma",0), "ability": rr.get("ability",0.0)})
                    used.add(rr.get("Zawodnik",""))

        pick("GP", "GP")
        pick("SCOC", "SCOC")

        out = pd.DataFrame(rows)
        if out.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Zawody","UM","Forma","ability"])
        out = out.sort_values(["Zawody","Kraj","ability"], ascending=[True, True, False], kind="mergesort").reset_index(drop=True)
        out.insert(0, "Lp.", np.arange(1, len(out)+1, dtype=int))
        return out

    def _players_from_quotas_jwc(self, sex: str, quotas_df=None):
        """
        Zwróć listę zawodników w kolejności:
        1) JWC (wiek ≤ 20, max 4/kraj, top ability),
        2) WC  (wg min(Kwota WC, r_wc)),
        3) COC (wg min(Kwota COC, max(r_coc - WC, 0))).
        """

        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Zawody","UM","Forma"])

        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]
        if "Kontuzja" in base.columns:
            k = pd.to_numeric(base["Kontuzja"], errors="coerce").fillna(0).astype(int)
            base = base[k.eq(0)]
        # ability + porządkowanie
        um = pd.to_numeric(base.get("UM", 50), errors="coerce").fillna(50)
        fo = pd.to_numeric(base.get("Forma", 50), errors="coerce").fillna(50)
        base["__ability"] = 0.65*um + 0.35*fo
        base["Kraj"] = base.get("Kraj","").astype(str).str.upper().str.strip()
        ps = pd.to_numeric(base.get("PrawoStartu", 0), errors="coerce").fillna(0).astype(int)
        base["__PS"] = ps

        # wiek ≤ 20 do JWC
        if "Wiek" in base.columns:
            age = pd.to_numeric(base["Wiek"], errors="coerce").fillna(0).astype(int)
        elif "Rok ur." in base.columns:
            age = (date.today().year - pd.to_numeric(base["Rok ur."], errors="coerce")).fillna(99).astype(int)
        else:
            age = pd.Series([99]*len(base), index=base.index, dtype=int)

        pool20 = base[age <= 20].copy()

        # ile wolnych miejsc wg quotas_df
        quotas_df = quotas_df.copy() if isinstance(quotas_df, pd.DataFrame) else pd.DataFrame(columns=["Kraj","JWC","WC","COC"])
        quotas_df["Kraj"] = quotas_df.get("Kraj","").astype(str).str.upper().str.strip()
        qmap = quotas_df.set_index("Kraj")[["JWC","WC","COC"]].fillna(0).astype(int).to_dict("index")

        picked = []

        def _take_from(pool, where_col: str, allowed_ps: set[int], per_nat_limit: dict[str,int] | None):
            nonlocal picked
            used = set((p["Zawodnik"], p["Kraj"]) for p in picked)
            rows = []
            # sort po ability ↓
            for nat, grp in pool.sort_values("__ability", ascending=False).groupby("Kraj", sort=False):
                need = max(0, int(qmap.get(nat, {}).get(where_col, 0)))
                if per_nat_limit:       # dla JWC limit 4/kraj (już w quotas_df jest liczba JWC, ale to „ile miejsc”, nie must-be-≤4 tutaj)
                    need = min(need, per_nat_limit.get(nat, 4))
                if need <= 0:
                    continue
                # filtr na prawa (dla WC/COC)
                gg = grp.copy()
                if where_col == "WC":
                    gg = gg[gg["__PS"].isin({1,2,3})]
                elif where_col == "COC":
                    gg = gg[gg["__PS"].isin(set(range(1,7)))]
                if gg.empty: 
                    continue
                for _, r in gg.iterrows():
                    key = (str(r.get("Zawodnik","")).strip(), str(r.get("Kraj","")).strip())
                    if key in used:
                        continue
                    rows.append({"Zawodnik":r.get("Zawodnik",""), "Kraj":r.get("Kraj",""),
                                "UM":r.get("UM",""), "Forma":r.get("Forma",""), "Zawody":where_col})
                    used.add(key)
                    need -= 1
                    if need <= 0:
                        break
            picked.extend(rows)

        # 1) JWC – z pool20 (≤20 lat), max 4/kraj
        _take_from(pool20, "JWC", allowed_ps=set(), per_nat_limit={})  # limit 4/kraj wynika z quotas_df["JWC"]

        # 2) WC – z całej bazy (z prawem 1–3), pomijając już wybranych
        _take_from(base, "WC", allowed_ps={1,2,3}, per_nat_limit=None)

        # 3) COC – 1–6, pomijając już wybranych
        _take_from(base, "COC", allowed_ps=set(range(1,7)), per_nat_limit=None)

        out = pd.DataFrame(picked, columns=["Zawodnik","Kraj","Zawody","UM","Forma"])
        if "Lp." not in out.columns:
            out.insert(0, "Lp.", range(1, len(out)+1))
        return out

    def _players_from_quotas_uni(self, sex: str, quotas_df=None):
        """
        Kolejność:
        1) UNI (wiek 18-25, max 4/kraj, top ability),
        2) WC  (PS 1–3),
        3) COC (PS 1–6),
        4) FC  (PS 1–7),
        z pominięciem już wybranych wyżej.
        """


        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Zawody","UM","Forma"])

        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]
        if "Kontuzja" in base.columns:
            k = pd.to_numeric(base["Kontuzja"], errors="coerce").fillna(0).astype(int)
            base = base[k.eq(0)]
        um = pd.to_numeric(base.get("UM", 50), errors="coerce").fillna(50)
        fo = pd.to_numeric(base.get("Forma", 50), errors="coerce").fillna(50)
        base["__ability"] = 0.65*um + 0.35*fo
        base["Kraj"] = base.get("Kraj","").astype(str).str.upper().str.strip()
        ps = pd.to_numeric(base.get("PrawoStartu", 0), errors="coerce").fillna(0).astype(int)
        base["__PS"] = ps

        # wiek
        if "Wiek" in base.columns:
            age = pd.to_numeric(base["Wiek"], errors="coerce").fillna(0).astype(int)
        elif "Rok ur." in base.columns:
            age = (date.today().year - pd.to_numeric(base["Rok ur."], errors="coerce")).fillna(99).astype(int)
        else:
            age = pd.Series([99]*len(base), index=base.index, dtype=int)

        pool_uni = base[(age >= 18) & (age <= 25)].copy()

        quotas_df = quotas_df.copy() if isinstance(quotas_df, pd.DataFrame) else pd.DataFrame(columns=["Kraj","UNI","WC","COC","FC"])
        quotas_df["Kraj"] = quotas_df.get("Kraj","").astype(str).str.upper().str.strip()
        # ile dostępnych miejsc per kraj w każdej kategorii
        qmap = quotas_df.set_index("Kraj")[["UNI","WC","COC","FC"]].fillna(0).astype(int).to_dict("index")

        picked = []

        def _take_from(pool, where_col: str, allowed_ps: set[int], per_nat_limit: dict[str,int] | None):
            nonlocal picked
            used = set((p["Zawodnik"], p["Kraj"]) for p in picked)
            rows = []
            # sort po ability ↓, a w ramach kraju pobieramy aż do wyczerpania „need”
            for nat, grp in pool.sort_values("__ability", ascending=False).groupby("Kraj", sort=False):
                need = max(0, int(qmap.get(nat, {}).get(where_col, 0)))
                if per_nat_limit:
                    need = min(need, per_nat_limit.get(nat, 4))
                if need <= 0:
                    continue
                gg = grp.copy()
                if allowed_ps:
                    gg = gg[gg["__PS"].isin(allowed_ps)]
                if gg.empty:
                    continue
                for _, r in gg.iterrows():
                    key = (str(r.get("Zawodnik","")).strip(), str(r.get("Kraj","")).strip())
                    if key in used:
                        continue
                    rows.append({"Zawodnik":r.get("Zawodnik",""), "Kraj":r.get("Kraj",""),
                                "UM":r.get("UM",""), "Forma":r.get("Forma",""), "Zawody":where_col})
                    used.add(key)
                    need -= 1
                    if need <= 0:
                        break
            picked.extend(rows)

        _take_from(pool_uni,"UNI", allowed_ps=set(),          per_nat_limit={})         # max 4/kraj już w qmap["UNI"]
        _take_from(base,    "WC",  allowed_ps={1,2,3},        per_nat_limit=None)
        _take_from(base,    "COC", allowed_ps=set(range(1,7)),per_nat_limit=None)
        _take_from(base,    "FC",  allowed_ps=set(range(1,8)),per_nat_limit=None)

        out = pd.DataFrame(picked, columns=["Zawodnik","Kraj","Zawody","UM","Forma"])
        if "Lp." not in out.columns:
            out.insert(0, "Lp.", range(1, len(out)+1))
        # postaraj się dobrać wiek jeśli jest w bazie
        if "Wiek" in base.columns and "Wiek" not in out.columns:
            out = out.merge(base[["Zawodnik","Kraj","Wiek"]], on=["Zawodnik","Kraj"], how="left")
            # uporządkuj kolumny
            cols = ["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"]
            out = out[[c for c in cols if c in out.columns] + [c for c in out.columns if c not in cols]]
        return out

    def _players_from_quotas_yog(self, sex: str, quotas_df=None):
        """
        Buduje prawą listę w zakładce Wybór-YOG.
        • YOG: wiek 14–18, max YOG[kraj] (bez ograniczeń PS), top po ability
        • WC:  PS ∈ {1,2,3}, max WC[kraj], bez zawodników już wybranych do YOG
        • COC: PS ∈ {1..6},  max COC[kraj], bez YOG/WC
        • FC:  PS ∈ {1..7},  max FC[kraj],  bez YOG/WC/COC
        Zwraca kolumny: Lp., Zawodnik, Kraj, Wiek, Zawody, UM, Forma
        """

        # 0) Źródło danych
        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        # 1) Filtr płci + normalizacja pól
        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == str(sex).upper()]
        if "Kontuzja" in base.columns:
            k = pd.to_numeric(base["Kontuzja"], errors="coerce").fillna(0).astype(int)
            base = base[k.eq(0)]
        base["Kraj"]  = base.get("Kraj","").astype(str).str.upper().str.strip()
        base["UM"]    = pd.to_numeric(base.get("UM",50),    errors="coerce").fillna(50.0)
        base["Forma"] = pd.to_numeric(base.get("Forma",50), errors="coerce").fillna(50.0)
        base["PrawoStartu"] = pd.to_numeric(base.get("PrawoStartu",0), errors="coerce").fillna(0).astype(int)

        # Wiek: akceptujemy kolumnę Wiek lub wyliczamy z "Rok ur."
        if "Wiek" in base.columns:
            age = pd.to_numeric(base["Wiek"], errors="coerce")
        elif "Rok ur." in base.columns:
            age = date.today().year - pd.to_numeric(base["Rok ur."], errors="coerce")
        else:
            age = pd.Series(np.nan, index=base.index, dtype=float)
        base["Wiek"] = age

        # ability (porządek wyboru w ramach kraju)
        base["__ability"] = 0.65*base["UM"] + 0.35*base["Forma"]

        # 2) Kwoty z lewej tabeli (lub przelicz, gdy brak)
        if quotas_df is None or quotas_df is Ellipsis or not isinstance(quotas_df, pd.DataFrame) or quotas_df.empty:
            try:
                quotas_df = self._compute_wybor_yog_quota(sex)
            except Exception:
                quotas_df = pd.DataFrame(columns=["Kraj","YOG","WC","COC","FC"])

        def _to_map(df, col):
            d = {}
            if df is None or df.empty or "Kraj" not in df.columns or col not in df.columns:
                return d
            tmp = df[["Kraj", col]].copy()
            tmp["Kraj"] = tmp["Kraj"].astype(str).str.upper().str.strip()
            tmp[col] = pd.to_numeric(tmp[col], errors="coerce").fillna(0).astype(int)
            for k, v in tmp.itertuples(index=False):
                if v > 0:
                    d[k] = int(v)
            return d

        qY = _to_map(quotas_df, "YOG")
        qW = _to_map(quotas_df, "WC")
        qC = _to_map(quotas_df, "COC")
        qF = _to_map(quotas_df, "FC")

        selected_names = set()   # by nie powielać
        blocks = []              # kolejność: YOG → WC → COC → FC

        def _pick(pool: pd.DataFrame, need_map: dict, label: str):
            if pool is None or pool.empty or not need_map:
                return pd.DataFrame(columns=["Zawodnik","Kraj","Wiek","Zawody","UM","Forma","__ability"])
            # usuń już wybranych
            p = pool[~pool["Zawodnik"].astype(str).isin(selected_names)].copy()
            if p.empty:
                return p

            out_rows = []
            for nat, grp in p.groupby("Kraj", sort=False):
                need = int(need_map.get(nat, 0))
                if need <= 0:
                    continue
                g = grp.sort_values("__ability", ascending=False, kind="mergesort").head(need)
                if not g.empty:
                    g = g[["Zawodnik","Kraj","Wiek","UM","Forma","__ability"]].copy()
                    g.insert(3, "Zawody", label)
                    out_rows.append(g)
            if not out_rows:
                return pd.DataFrame(columns=["Zawodnik","Kraj","Wiek","Zawody","UM","Forma","__ability"])
            out = pd.concat(out_rows, ignore_index=True)
            for n in out["Zawodnik"].astype(str):
                selected_names.add(n)
            return out

        # 3) YOG: tylko 14–18 (włącznie); akceptujemy NaN wieku jako NIE-YOG
        pool_yog = base[(base["Wiek"].between(14, 18, inclusive="both"))].copy()
        blocks.append(_pick(pool_yog, qY, "YOG"))

        # 4) WC / COC / FC – z reszty (wiek dowolny), z odpowiednimi PS
        pool_rest = base.copy()
        blocks.append(_pick(pool_rest[pool_rest["PrawoStartu"].isin({1,2,3})],        qW, "WC"))
        blocks.append(_pick(pool_rest[pool_rest["PrawoStartu"].isin(set(range(1,7)))], qC, "COC"))
        blocks.append(_pick(pool_rest[pool_rest["PrawoStartu"].isin(set(range(1,8)))], qF, "FC"))

        df = pd.concat([b for b in blocks if b is not None and not b.empty], ignore_index=True) \
                if any((b is not None and not b.empty) for b in blocks) \
                else pd.DataFrame(columns=["Zawodnik","Kraj","Wiek","Zawody","UM","Forma","__ability"])

        if df.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        # 5) Kolejność w tabeli: YOG → WC → COC → FC, w obrębie grupy top ability
        order = {"YOG":0, "WC":1, "COC":2, "FC":3}
        df["__ord"] = df["Zawody"].map(order).fillna(99).astype(int)
        df = df.sort_values(["__ord","__ability"], ascending=[True, False], kind="mergesort") \
            .reset_index(drop=True)

        df.insert(0, "Lp.", range(1, len(df)+1))
        df = df[["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"]]
        return df

    ### NEW: pomocnik – przefiltruj DF wg płci + zawodów z użyciem Twoich reguł PS
    def _filter_df_for_comp_sex(self, df, comp: str, sex: str):
        # NIE mieszamy UI – tymczasowo podmieniamy wartości i przywracamy
        old_gender = getattr(self, "var_f_gender", None).get() if hasattr(self, "var_f_gender") else "WSZYSCY"
        old_comp   = getattr(self, "var_f_comp", None).get() if hasattr(self, "var_f_comp") else "WSZYSCY"
        old_rules  = getattr(self, "var_f_use_ps_rules", None).get() if hasattr(self, "var_f_use_ps_rules") else True
        old_level  = getattr(self, "var_f_level", None).get() if hasattr(self, "var_f_level") else "WSZYSCY"
        try:
            if hasattr(self, "var_f_gender"): self.var_f_gender.set(sex)
            if hasattr(self, "var_f_level"):  self.var_f_level.set("WSZYSCY")
            if hasattr(self, "var_f_comp"):   self.var_f_comp.set(comp)
            if hasattr(self, "var_f_use_ps_rules"): self.var_f_use_ps_rules.set(True)
            return self._filter_df_by_ui(df)
        except Exception:
            return df.copy()
        finally:
            try:
                if hasattr(self, "var_f_gender"): self.var_f_gender.set(old_gender)
                if hasattr(self, "var_f_level"):  self.var_f_level.set(old_level)
                if hasattr(self, "var_f_comp"):   self.var_f_comp.set(old_comp)
                if hasattr(self, "var_f_use_ps_rules"): self.var_f_use_ps_rules.set(old_rules)
            except Exception:
                pass

    def _players_from_jun_countries(self, sex: str, per_country: int = 3):
        """
        Zwraca DF juniorów dla podanej płci (M/W) – po `per_country` z każdego kraju,
        który jest obecny w tabelach JUN-M / JUN-W (Kwoty Startowe → JUN).
        Kolumny: Lp., Zawodnik, Kraj, UM, Forma, Zawody
        """
        

        # 1) baza zawodników z cache
        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","UM","Forma","Zawody"])

        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]

        # 2) kraje z odpowiedniej tabeli JUN-M / JUN-W (jednokolumnowe „Kraj”)
        qt = getattr(self, "quota_tables", {}) or {}
        key = f"JUN-{sex}"
        if key not in qt:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","UM","Forma","Zawody"])

        try:
            df_countries = self._table_to_df(qt[key])
        except Exception:
            df_countries = pd.DataFrame(columns=["Kraj"])

        if "Kraj" not in df_countries.columns:
            # stare wersje mogły trzymać to w kolumnie „Pozycja”, którą mapujemy na „Kraj”
            if "Pozycja" in df_countries.columns:
                df_countries = df_countries.rename(columns={"Pozycja":"Kraj"})
            else:
                df_countries = pd.DataFrame(columns=["Kraj"])

        nats = (
            df_countries["Kraj"]
            .dropna().astype(str).str.upper().str.strip()
            .unique().tolist()
        )

        if not nats:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","UM","Forma","Zawody"])

        # 3) ograniczenie do juniorów wg Twojego filtra dla zawodów "JUN"
        pool = self._filter_df_for_comp_sex(base, "JUN", sex).copy()

        if pool.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","UM","Forma","Zawody"])

        # 4) „siła” jak przy WC/COC/FC
        um = pd.to_numeric(pool.get("UM", 50), errors="coerce").fillna(50)
        forma = pd.to_numeric(pool.get("Forma", 50), errors="coerce").fillna(50)
        pool["__ability"] = 0.65 * um + 0.35 * forma

        # 5) zbierz po `per_country` na kraj
        out_rows = []
        for nat in nats:
            cand = pool[pool["Kraj"].astype(str).str.upper() == nat].copy()
            if cand.empty:
                continue
            cand = cand.sort_values("__ability", ascending=False, kind="mergesort").head(int(per_country))
            if not cand.empty:
                # ustal nazwę cyklu JUN w zależności od tabeli źródłowej
                comp_name = None
                for prefix in ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]:
                    tab_key = f"{prefix}-{sex}"
                    if tab_key in (self.quota_tables or {}):
                        try:
                            df_src = self._table_to_df(self.quota_tables[tab_key])
                            if nat in df_src["Kraj"].astype(str).str.upper().values:
                                comp_name = tab_key
                                break
                        except Exception:
                            pass
                if comp_name is None:
                    comp_name = f"JUN-{sex}"

                comp_name = self._jun_comp_for_nat(sex, nat)
                out_rows.append(
                    cand.assign(Zawody=comp_name)[["Zawodnik","Kraj","UM","Forma","Zawody"]]
                )

        if not out_rows:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","UM","Forma","Zawody"])

        res = pd.concat(out_rows, ignore_index=True)

        # wstaw „Lp.” na 1. miejscu
        res.insert(0, "Lp.", range(1, len(res)+1))
        return res
    
    ### NEW: budowa listy zawodników na podstawie kwot (WC/COC/FC)
    def _players_from_quotas(self, sex: str, quotas_df=None):
        """
        Buduje listę zawodników z uwzględnieniem limitów.
        Jeśli quotas_df jest podany (Kraj, WC, COC, FC), używa go zamiast domyślnych kwot.
        """
        # Jeśli przyszły gotowe kwoty – nadpisujemy mapę kraj→limity
        quota_map_override = None
        if quotas_df is not None and len(quotas_df) > 0:
            quota_map_override = {
                str(row["Kraj"]).upper().strip(): {
                    "WC":  int(row.get("WC", 0)),
                    "COC": int(row.get("COC", 0)),
                    "FC":  int(row.get("FC", 0)),
                }
                for _, row in quotas_df.iterrows()
            }

        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Zawodnik", "Kraj", "Zawody", "UM", "Forma"])

        # tylko dana płeć
        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]
        if "JUN/SEN" in base.columns:
            base = base[base["JUN/SEN"].astype(str).str.upper().isin(["SEN", "SENIOR", "S"])]
        # kolejność priorytetów między cyklami
        comp_order = ("WC", "COC", "FC")

        # override kwot z gotowego df (jeśli podano)
        quota_override = None
        if quotas_df is not None and len(quotas_df) > 0:
            _qdf = quotas_df.copy()
            _qdf["Kraj"] = _qdf["Kraj"].astype(str).str.upper().str.strip()
            quota_override = {
                "WC":  dict(zip(_qdf["Kraj"], _qdf["WC"].astype(int))),
                "COC": dict(zip(_qdf["Kraj"], _qdf["COC"].astype(int))),
                "FC":  dict(zip(_qdf["Kraj"], _qdf["FC"].astype(int))),
            }

        out_rows = []
        used = set()  # globalny zbiór: „nazwisko_norm|KRAJ”

        for comp in comp_order:
            # kwoty dla danego comp i płci
            try:
                if quota_override is not None:
                    quotas = quota_override.get(comp, {}) or {}
                else:
                    quotas = self._compute_quota_map(f"{comp}-{sex}") or {}
            except Exception:
                quotas = {}

            # kandydaci zgodnie z Twoimi regułami PS/wieku dla tego comp
            pool = self._filter_df_for_comp_sex(base, comp, sex).copy()
            if pool.empty:
                continue

            # siła zawodnika
            um = pd.to_numeric(pool.get("UM", 50), errors="coerce").fillna(50)
            forma = pd.to_numeric(pool.get("Forma", 50), errors="coerce").fillna(50)
            pool["__ability"] = 0.65 * um + 0.35 * forma

            # klucz do deduplikacji (nazwa unormowana + kraj)
            pool["__key"] = (
                pool["Zawodnik"].map(_norm_name_key) + "|" +
                pool["Kraj"].astype(str).str.upper()
            )

            # selekcja per kraj wg kwot, pomijając już użytych
            for nat, cnt in quotas.items():
                cnt = int(cnt or 0)
                if cnt <= 0:
                    continue

                cand = pool[pool["Kraj"].astype(str).str.upper() == str(nat).upper()].copy()
                if cand.empty:
                    continue

                cand = cand.sort_values("__ability", ascending=False, kind="mergesort")
                cand = cand[~cand["__key"].isin(used)]  # ← deduplikacja między cyklami
                take = cand.head(cnt)

                if take.empty:
                    continue

                comp_name = comp            # "WC-M", "COC-W", "FC-M", ...
                # <<< KLUCZOWE: dodajemy 'take', a nie całe 'cand' >>>
                out_rows.append(
                    take.assign(Zawody=comp_name)[["Zawodnik","Kraj","UM","Forma","Zawody"]]
                )
                used.update(take["__key"].tolist())

        if not out_rows:
            return pd.DataFrame(columns=["Zawodnik", "Kraj", "Zawody", "UM", "Forma"])

        res = pd.concat(out_rows, ignore_index=True)
        return res[["Zawodnik", "Kraj", "Zawody", "UM", "Forma"]].copy()

    def _refresh_wybor_ch_tab(self, sex: str):
        """
        Odśwież lewą i prawą tabelę w Wybór-CH (OG/WCH/SFWC-<sex>).
        """
        
        # 1) Kraj – WC – COC – FC
        try:
            dfc = self._compute_wybor_ch_quota(sex)
        except Exception:
            dfc = pd.DataFrame(columns=["Kraj","WC","COC","FC"])

        targets = self._wyborCH_countries.get(sex, [])
        if not isinstance(targets, (list, tuple)):
            targets = [targets]
        for t in targets:
            try:
                t.set_dataframe(dfc)
            except Exception:
                pass

        # 2) Zawodnicy (na bazie wyliczonych kwot CH)
        try:
            dfp = self._players_from_quotas(sex, quotas_df=dfc)
        except Exception:
            dfp = pd.DataFrame(columns=["Zawodnik","Kraj","Zawody","UM","Forma"])

        targets = self._wyborCH_players.get(sex, [])
        if not isinstance(targets, (list, tuple)):
            targets = [targets]
        for t in targets:
            try:
                t.set_dataframe(dfp)
            except Exception:
                pass

    ### NEW: odśwież obie tabele w zakładce Wybór-*
    def _refresh_wybor_tab(self, sex: str):
        
        # 1) Kraj – WC – COC – FC (efektywne kwoty wg logiki min+odejmowania)
        try:
            dfc = self._compute_wybor_min_quota(sex)
        except Exception:
            dfc = pd.DataFrame(columns=["Kraj","WC","COC","FC"])

        targets = self._wybor_countries.get(sex, [])
        if not isinstance(targets, (list, tuple)):
            targets = [targets]
        for t in targets:
            try:
                t.set_dataframe(dfc)
            except Exception:
                pass

        # 2) Zawodnicy – buduj z *efektywnych* kwot
        try:
            dfp = self._players_from_quotas(sex, quotas_df=dfc)
        except Exception:
            dfp = pd.DataFrame(columns=["Zawodnik","Kraj","Zawody","UM","Forma"])

        targets = self._wybor_players.get(sex, [])
        if not isinstance(targets, (list, tuple)):
            targets = [targets]
        for t in targets:
            try:
                t.set_dataframe(dfp)
            except Exception:
                pass

        self._wybor_last_dfc = getattr(self, "_wybor_last_dfc", {})
        self._wybor_last_dfc[sex] = dfc.copy() if hasattr(dfc, "copy") else dfc
        try:
            self.after_idle(lambda s=sex: self._update_wybor_sums(s, self._wybor_last_dfc[s]))
        except Exception:
            self._update_wybor_sums(sex, dfc)
    
    def _on_refresh_from_quotas(self, sex):
        self._refresh_wybor_tab(sex)
        dfc = getattr(self, "_wybor_last_dfc", {}).get(sex)
        if dfc is not None:
            self._update_wybor_sums(sex, dfc)

    def _update_wybor_sums(self, sex: str, df):
        
        # słownik { 'M': (var_wc, var_coc, var_fc), 'W': (...) }
        self._wybor_sumvars = getattr(self, "_wybor_sumvars", {})
        vars_tuple = self._wybor_sumvars.get(sex)
        if not vars_tuple:
            return
        var_wc, var_coc, var_fc = vars_tuple

        def _sum(col):
            try:
                return int(pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0).sum())
            except Exception:
                return 0

        var_wc.set(f"WC: {_sum('WC')}")
        var_coc.set(f"COC: {_sum('COC')}")
        var_fc.set(f"FC: {_sum('FC')}")

    # === sortowanie tabeli zawodników z auto-REBIND po każdym odświeżeniu ===
    def _install_players_sort(self, tbl, comp_order=("YOG","WC","COC","FC")):
        

        tv = getattr(tbl, "tv_main", getattr(tbl, "tree", None))
        if tv is None:
            return

        # per-tabela stan sortowania i konfiguracja
        if not hasattr(tbl, "_players_sort_state"):
            tbl._players_sort_state = {}
        tbl._players_comp_order = tuple(comp_order)

        def _get_df():
            return getattr(tbl, "_last_df", None)

        def _apply_df(df_new: pd.DataFrame):
            # 1) odśwież dane
            df2 = df_new.copy()
            if "Lp." in df2.columns:
                df2 = df2.drop(columns=["Lp."])
            df2.insert(0, "Lp.", range(1, len(df2) + 1))
            tbl.set_dataframe(df2)
            try:
                tbl.autosize_columns()
            except Exception:
                pass
            setattr(tbl, "_last_df", df2)

            # 2) REBIND nagłówków (po set_dataframe Treeview traci command)
            def _bind_headers():
                tv2 = getattr(tbl, "tv_main", getattr(tbl, "tree", None)) or tv
                cols = [c for c in tv2["columns"]
                        if c in ("Zawodnik","Kraj","Wiek","Zawody","UM","Forma")]
                for c in cols:
                    tv2.heading(c, text=c, command=(lambda _c=c: _sort_by(_c)))
            # po krótkim „after” mamy pewność, że kolumny istnieją
            try:
                tbl.after(0, _bind_headers)
            except Exception:
                _bind_headers()

        def _sort_by(col: str):
            df = _get_df()
            if df is None or df.empty or col not in df.columns:
                return
            asc = not tbl._players_sort_state.get(col, False)  # toggle

            if col == "Zawody":
                order = pd.Categorical(
                    df["Zawody"].astype(str).str.upper(),
                    categories=[c.upper() for c in tbl._players_comp_order],
                    ordered=True
                )
                if "__ability" in df.columns:
                    df_sorted = (
                        df.assign(__ord=order)
                        .sort_values(["__ord","__ability"], ascending=[asc, False], kind="mergesort")
                        .drop(columns="__ord")
                    )
                else:
                    df_sorted = (
                        df.assign(__ord=order)
                        .sort_values(["__ord","Zawodnik"], ascending=[asc, True], kind="mergesort")
                        .drop(columns="__ord")
                    )
            else:
                df_sorted = df.copy()
                if col in ("UM","Forma","Wiek"):
                    df_sorted[col] = pd.to_numeric(df_sorted[col], errors="coerce")
                df_sorted = df_sorted.sort_values(col, ascending=asc, kind="mergesort")

            tbl._players_sort_state[col] = asc
            _apply_df(df_sorted)

        # pierwszy bind (żeby działało od razu, bez sortowania)
        _apply_df(getattr(tbl, "_last_df", pd.DataFrame()))

    def _reset_and_set_table_frozen(self, tree_attr: str, parent, df: pd.DataFrame):
        old = getattr(self, tree_attr, None)
        try:
            if old is not None:
                old.destroy()
        except Exception:
            pass
        t = FrozenFirstColTable(parent, frozen_col="Miejsce")
        t.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        t.pack(fill=tk.BOTH, expand=True)
        setattr(self, tree_attr, t)
        t.set_dataframe(df)

    def _open_injury_update_dialog(self):

        try:
            parent = self.winfo_toplevel()
        except Exception:
            parent = self

        top = tk.Toplevel(parent)
        top.title("Aktualizacja bazy po Upadkach")
        try: top.transient(parent)
        except Exception: pass
        try: top.grab_set()
        except Exception: pass

        ttk.Label(top, text="Zawody (opis):").grid(row=0, column=0, sticky="e", padx=8, pady=6)
        e_event = ttk.Entry(top, width=32)
        e_event.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        # auto-uzupełnij z aktualnie wybranej skoczni – wyciągnij [TAG] z etykiety
        try:
            import re as _re
            _hill_label = self.var_hill_pick.get().strip()
            _m = _re.match(r"^\[([^\]]+)\]", _hill_label)
            _event_default = _m.group(1) if _m else _hill_label
            e_event.insert(0, _event_default)
        except Exception:
            pass

        ttk.Label(top, text="Week:").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        sp_week = ttk.Spinbox(top, from_=0, to=200, width=8)
        try:
            _week_default = self.var_week_pick.get().strip()
            sp_week.set(int(_week_default) if _week_default.isdigit() else 0)
        except Exception:
            try: sp_week.set(0)
            except Exception: pass
        sp_week.grid(row=1, column=1, sticky="w", padx=8, pady=6)

        def _ok():
            try: event_name = e_event.get().strip()
            except Exception: event_name = ""
            try: week_val = int(sp_week.get())
            except Exception: week_val = 0
            try: top.destroy()
            except Exception: pass
            try:
                self._apply_injury_updates_to_db(event_name, week_val)
            except Exception as e:
                try: messagebox.showerror("Aktualizacja bazy", f"Wystąpił błąd:\n{e}")
                except Exception: pass

        btns = ttk.Frame(top)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", padx=8, pady=(6,8))
        ttk.Button(btns, text="OK", command=_ok).pack(side=tk.RIGHT, padx=(6,0))
        ttk.Button(btns, text="Anuluj", command=top.destroy).pack(side=tk.RIGHT)

        # wyciągnij okno na wierzch
        try:
            top.update_idletasks()
            top.lift(); top.focus_force()
            top.attributes("-topmost", True); top.after(250, lambda: top.attributes("-topmost", False))
        except Exception:
            pass

    def _apply_injury_updates_to_db(self, event_name: str, week_val: int):
        

        falls_agg = getattr(self, "_falls_last_agg", None)
        falls_df  = getattr(self, "_falls_last_df",  None)

        if not isinstance(falls_agg, pd.DataFrame) or falls_agg.empty:
            if isinstance(falls_df, pd.DataFrame) and not falls_df.empty:
                cols = [c for c in ["Zawodnik","Kraj","Kontuzja (dni)","Długość kontuzji (WEEK)","ΔUM (kontuzja)","ΔForma (kontuzja)"] if c in falls_df.columns]
                if len(cols) >= 3:
                    tmp = falls_df[cols].copy()
                    agg_map = {}
                    if "Kontuzja (dni)" in tmp.columns: agg_map["Kontuzja (dni)"] = "max"
                    if "ΔUM (kontuzja)" in tmp.columns: agg_map["ΔUM (kontuzja)"] = "min"
                    if "ΔForma (kontuzja)" in tmp.columns: agg_map["ΔForma (kontuzja)"] = "min"
                    if agg_map:
                        falls_agg = tmp.groupby(["Zawodnik","Kraj"], as_index=False).agg(agg_map)

        if not isinstance(falls_agg, pd.DataFrame) or falls_agg.empty:
            messagebox.showinfo("Aktualizacja bazy", "Brak danych o kontuzjach (Upadki). Najpierw uruchom symulację z upadkami.")
            return

        weeks_col = None
        if isinstance(falls_df, pd.DataFrame) and not falls_df.empty:
            for c in falls_df.columns:
                if str(c).strip().lower().startswith("długość kontuzji"):
                    weeks_col = c; break

        if weeks_col:
            w = falls_df[["Zawodnik","Kraj",weeks_col]].groupby(["Zawodnik","Kraj"], as_index=False)[weeks_col].max()
            falls_agg = falls_agg.merge(w, on=["Zawodnik","Kraj"], how="left")
            falls_agg["Długość kontuzji (WEEK)"] = falls_agg[weeks_col]
        else:
            if "Kontuzja (dni)" in falls_agg.columns:
                dd = pd.to_numeric(falls_agg["Kontuzja (dni)"], errors="coerce").fillna(0).astype(int)
                falls_agg["Długość kontuzji (WEEK)"] = dd.map(lambda d: 0 if d<=5 else (1 + (d-6)//7))
            else:
                falls_agg["Długość kontuzji (WEEK)"] = 0

        falls_agg["ReturnWeek"] = pd.to_numeric(week_val) + pd.to_numeric(falls_agg["Długość kontuzji (WEEK)"], errors="coerce").fillna(0).astype(int) + 1

        path = os.path.join("S45", "Zawodnicy S45gpt.csv")
        if not os.path.exists(path):
            # fallback: szukaj względem skryptu
            _base = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(_base, "S45", "Zawodnicy S45gpt.csv")
        if not os.path.exists(path):
            messagebox.showerror("Aktualizacja bazy", f"Nie znaleziono pliku:\n{path}")
            return

        def _read_any(p):
            try: return pd.read_csv(p)
            except Exception: pass
            for args in ({"sep":";"},{"sep":";","encoding":"cp1250"},{"sep":",","encoding":"utf-8"}):
                try: return pd.read_csv(p, **args)
                except Exception: continue
            try: return pd.read_excel(p)
            except Exception: return None

        db = _read_any(path)
        if not isinstance(db, pd.DataFrame) or db.empty:
            messagebox.showerror("Aktualizacja bazy", "Nie udało się wczytać bazy zawodników.")
            return

        rename_map = {}
        for c in list(db.columns):
            u = str(c).strip().lower()
            if u in ("zawodnik","jumper","name"): rename_map[c] = "Zawodnik"
            elif u in ("kraj","nat","code"):      rename_map[c] = "Kraj"
            elif u.startswith("um"):              rename_map[c] = "UM"
            elif u.startswith("forma"):           rename_map[c] = "Forma"
            elif u.startswith("kontuzja"):        rename_map[c] = "Kontuzja"
        if rename_map: db = db.rename(columns=rename_map)

        for _, r in falls_agg.iterrows():
            name = str(r.get("Zawodnik","")).strip()
            nat  = str(r.get("Kraj","")).strip()
            dUM  = int(r.get("ΔUM (kontuzja)", 0) or 0)
            dFR  = int(r.get("ΔForma (kontuzja)", 0) or 0)
            retW = int(r.get("ReturnWeek", 0) or 0)

            col_z = db["Zawodnik"] if "Zawodnik" in db.columns else pd.Series([""] * len(db))
            col_k = db["Kraj"]     if "Kraj"     in db.columns else pd.Series([""] * len(db))
            mask = col_z.astype(str).str.strip().eq(name) & col_k.astype(str).str.strip().eq(nat)
            if not hasattr(mask, "any") or not mask.any(): continue

            if "UM" in db.columns:
                db.loc[mask, "UM"] = pd.to_numeric(db.loc[mask, "UM"], errors="coerce").fillna(0).astype(int) + dUM
                db.loc[mask, "UM"] = db.loc[mask, "UM"].clip(lower=0)
            if "Forma" in db.columns:
                db.loc[mask, "Forma"] = pd.to_numeric(db.loc[mask, "Forma"], errors="coerce").fillna(0).astype(int) + dFR
                db.loc[mask, "Forma"] = db.loc[mask, "Forma"].clip(lower=0)

            if "Kontuzja" in db.columns:
                db.loc[mask, "Kontuzja"] = retW
            else:
                db["Kontuzja"] = 0
                db.loc[mask, "Kontuzja"] = retW

        try:
            if path.lower().endswith((".xlsx",".xls")):
                with pd.ExcelWriter(path, engine="openpyxl", mode="w") as w:
                    db.to_excel(w, index=False, sheet_name="Zawodnicy")
            else:
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        head = fh.read(2000)
                    sep = ";" if ";" in head and head.count(";") >= head.count(",") else ","
                except Exception:
                    sep = ";"
                db.to_csv(path, index=False, sep=sep, encoding="utf-8-sig")
        except Exception as e:
            messagebox.showerror("Aktualizacja bazy", f"Nie udało się zapisać zmian:\n{e}")
            return

                # === DOPISZ DO "Kontuzje S45.csv" – LOG WSZYSTKICH KONTUZJOWANYCH (robust) ===
        try:
            
            falls_df_src  = falls_df if isinstance(falls_df, pd.DataFrame) else getattr(self, "_falls_last_df", None)
            falls_agg_src = falls_agg if isinstance(falls_agg, pd.DataFrame) else getattr(self, "_falls_last_agg", None)

            # 1) Baza: tylko kontuzje realne (dni>0 LUB week>0) z agregatu
            base = pd.DataFrame()
            if isinstance(falls_agg_src, pd.DataFrame) and not falls_agg_src.empty:
                base = falls_agg_src.copy()
                if "Kontuzja (dni)" in base.columns:
                    base["Kontuzja (dni)"] = pd.to_numeric(base["Kontuzja (dni)"], errors="coerce").fillna(0).astype(int)
                else:
                    base["Kontuzja (dni)"] = 0
                if "Długość kontuzji (WEEK)" in base.columns:
                    base["Długość kontuzji (WEEK)"] = pd.to_numeric(base["Długość kontuzji (WEEK)"], errors="coerce").fillna(0).astype(int)
                else:
                    base["Długość kontuzji (WEEK)"] = 0
                base = base[(base["Kontuzja (dni)"] > 0) | (base["Długość kontuzji (WEEK)"] > 0)]
            else:
                base = pd.DataFrame(columns=["Zawodnik","Kraj","Kontuzja (dni)","Długość kontuzji (WEEK)","ΔUM (kontuzja)","ΔForma (kontuzja)"])

            wrote_n = 0
            csv_path = "Kontuzje S45.csv"
            try:
                csv_path = _find_nearby_file(csv_path) or csv_path
            except Exception:
                pass

            if not base.empty:
                # 2) Meta z ostatnich Upadków (Lekarz, Infrastruktura, Kontuzja (rodzaj), Kontuzja (dni))
                meta = pd.DataFrame()
                if isinstance(falls_df_src, pd.DataFrame) and not falls_df_src.empty:
                    tmp = falls_df_src.copy()
                    if "Kontuzja (dni)" in tmp.columns:
                        tmp["_dni_"] = pd.to_numeric(tmp["Kontuzja (dni)"], errors="coerce").fillna(0).astype(int)
                        tmp = tmp.sort_values(["Zawodnik","Kraj","_dni_"], ascending=[True, True, False])                          .drop_duplicates(subset=["Zawodnik","Kraj"], keep="first")
                    cols = ["Zawodnik","Kraj"]
                    for c in ("Infrastruktura","Lekarz","Kontuzja (rodzaj)","Kontuzja (dni)"):
                        if c in tmp.columns: cols.append(c)
                    meta = tmp[cols].copy()

                inj_rows = base.merge(meta, on=["Zawodnik","Kraj"], how="left")

                # 3) Kolumny stałe i obliczenia
                inj_rows.insert(0, "Zawody", event_name or "")
                try:
                    week_int = int(float(week_val))
                except Exception:
                    try:
                        week_int = int(pd.to_numeric([week_val], errors="coerce").fillna(0).iloc[0])
                    except Exception:
                        week_int = 0
                inj_rows.insert(1, "Week", week_int)

                inj_rows["UM"]    = pd.to_numeric(inj_rows.get("ΔUM (kontuzja)", 0), errors="coerce").fillna(0).astype(int)
                inj_rows["Forma"] = pd.to_numeric(inj_rows.get("ΔForma (kontuzja)", 0), errors="coerce").fillna(0).astype(int)

                weeks_col = "Długość kontuzji (WEEK)"
                inj_rows[weeks_col] = pd.to_numeric(inj_rows.get(weeks_col, 0), errors="coerce").fillna(0).astype(int)
                inj_rows["Powrót"]  = inj_rows["Week"] + inj_rows[weeks_col]

                required_order = ["Zawody","Week","Zawodnik","Kraj","Infrastruktura","Lekarz",
                                  "Kontuzja (rodzaj)","Kontuzja (dni)","Długość kontuzji (WEEK)","UM","Forma","Powrót"]
                for c in required_order:
                    if c not in inj_rows.columns:
                        inj_rows[c] = pd.NA
                inj_rows = inj_rows[required_order].copy()

                # 4) Dopisz/utwórz CSV (średnik + BOM)
                def _read_csv_any(p):
                    for sep in (";", ","):
                        for enc in ("utf-8-sig","utf-8","cp1250","latin1"):
                            try:
                                return pd.read_csv(p, sep=sep, engine="python", encoding=enc)
                            except Exception:
                                pass
                    return None

                old = _read_csv_any(csv_path)
                if isinstance(old, pd.DataFrame) and not old.empty:
                    key = ["Zawody","Week","Zawodnik","Kraj"]
                    out = (pd.concat([old, inj_rows], ignore_index=True)
                             .drop_duplicates(subset=key, keep="last"))
                else:
                    out = inj_rows

                out.to_csv(csv_path, index=False, sep=";", encoding="utf-8-sig")
                wrote_n = len(inj_rows)

            # Info diagnostyczna (stdout)
            try:
                _abs = os.path.abspath(csv_path)
                print(f"[Kontuzje CSV] dopisano {wrote_n} wierszy → {_abs}")
            except Exception:
                pass

        except Exception as _inj_csv_e:
            try:
                print("[WARN] Kontuzje CSV:", _inj_csv_e)
            except Exception:
                pass
        # --- KONIEC dopisku do 'Kontuzje S45.csv' ---

        messagebox.showinfo("Aktualizacja bazy",
                    f"Zaktualizowano zawodników: {len(falls_agg)}\n"
                    f"Zawody: {event_name or '(nie podano)'}\n"
                    f"Week bazowy: {week_val} (powrót = Week + Długość kontuzji)"
                )

    def __init__(self, parent):
        super().__init__(parent)
        # pamięć "zużytych" slotów per Kraj i płeć (np. "SLO#M" -> 7)
        self._quota_used_count = {}
        self.var_quota_append = tk.BooleanVar(value=False)
        self.pack(fill=tk.BOTH, expand=True)
        self._build()

    def _build(self):
        nb = ttk.Notebook(self); nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.nb = nb

        self.tab_db = ttk.Frame(nb)
        self._build_db_tab(self.tab_db)
        self.tab_quotas = ttk.Frame(nb)
        self.tab_filter = ttk.Frame(nb)
        self.tab_roster = ttk.Frame(nb)
        self.tab_params = ttk.Frame(nb)
        self.tab_preview = ttk.Frame(nb)
        self.tab_ko50_main = ttk.Frame(nb)
        self.tab_ko64_main = ttk.Frame(nb)
        self.tab_ko_ll = ttk.Frame(nb)
        self.tab_falls = ttk.Frame(nb)
        nb.add(self.tab_db, text="Baza zawodników")
        self.tab_klasyfikacje = KlasyfikacjeTab(self.nb, default_excel="Klasyfikacje2 S44 — kopia.xlsx")
        self.nb.add(self.tab_klasyfikacje, text="Klasyfikacje")
        nb.add(self.tab_quotas, text="Kwoty Startowe")
        nb.add(self.tab_roster, text="Zawodnicy")
        nb.add(self.tab_params, text="Parametry")
        nb.add(self.tab_preview, text="Podgląd wyników")
        nb.add(self.tab_ko50_main, text="KO 50")
        nb.add(self.tab_ko64_main, text="KO 64")
        nb.add(self.tab_falls, text="Upadki")
        # --- Toolbar Upadki: aktualizacja bazy po kontuzjach ---
        try:
            bar_falls = ttk.Frame(self.tab_falls)
            bar_falls.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6,0))
            ttk.Button(
                bar_falls,
                text="Aktualizuj bazę z Upadków…",
                command=self._open_injury_update_dialog
            ).pack(side=tk.LEFT)
        except Exception as _e:
            pass

        self._build_quotas_tab(self.tab_quotas)

        # --- Pod-notebook dla KO 50 ---
        self.nb_ko50 = ttk.Notebook(self.tab_ko50_main)
        self.nb_ko50.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Pod-zakładki KO 50 (utrzymujemy te same atrybuty jak wcześniej!)
        self.tab_ko50_pairs = ttk.Frame(self.nb_ko50)
        self.tab_ko_ll      = ttk.Frame(self.nb_ko50)
        self.nb_ko50.add(self.tab_ko50_pairs, text="Pary (R1)")
        self.nb_ko50.add(self.tab_ko_ll, text="Lucky Losers")

        # --- Pod-notebook dla KO 64 ---
        self.nb_ko64 = ttk.Notebook(self.tab_ko64_main)
        self.nb_ko64.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Pod-zakładki KO 64 (utrzymujemy te same atrybuty jak wcześniej!)
        self.tab_ko64_bracket_tbl = ttk.Frame(self.nb_ko64)
        self.tab_ko64_bracket     = ttk.Frame(self.nb_ko64)
        self.tab_ko64_klasyf      = ttk.Frame(self.nb_ko64)

        self.nb_ko64.add(self.tab_ko64_bracket_tbl, text="Drabinka (tabela)")
        self.nb_ko64.add(self.tab_ko64_bracket, text="Drabinka (grafika)")
        self.nb_ko64.add(self.tab_ko64_klasyf, text="Klasyfikacja")

        self._build_ko64_klasyfikacja(self.tab_ko64_klasyf)
        # params
        left = ttk.Frame(self.tab_params); right = ttk.Frame(self.tab_params)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8,4), pady=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4,8), pady=8)

        sec_files = Labeled(left, "Pliki i ścieżki"); sec_files.pack(fill=tk.X, pady=(0,8))
        self.var_excel = tk.StringVar(value=getattr(sim, "DEFAULT_EXCEL", ""))
        self.var_outdir = tk.StringVar(value=str(Path("./wyniki").resolve()))
        file_row(sec_files.body, "Plik zawodników (CSV/XLSX) (—excel)", self.var_excel, self.pick_excel)
        file_row(sec_files.body, "Folder wyników (—outdir)", self.var_outdir, self.pick_outdir, is_dir=True)

        sec_hill = Labeled(left, "Skocznia"); sec_hill.pack(fill=tk.X, pady=(0,8))
        self.var_hill = tk.StringVar(value="Zakopane")
        self.var_k = tk.IntVar(value=125)
        self.var_hs = tk.IntVar(value=140)
        self.var_meter = tk.StringVar(value="")
        grid_entries(sec_hill.body, [
            ("Nazwa (—hill-name)", self.var_hill, None),
            ("K (—k)", self.var_k, int),
            ("HS (—hs)", self.var_hs, int),
            ("Punkty za metr (—meter) puste=auto", self.var_meter, float),
        ])
        # ——— Wybór z listy skoczni (CSV) ———
        self.var_hills_csv = tk.StringVar(value="S45/Skocznie S45.csv")

        row = ttk.Frame(sec_hill.body); row.grid(row=4, column=0, columnspan=3, sticky="we", pady=(6,0))
        row.columnconfigure(1, weight=1)

        ttk.Label(row, text="Plik skoczni:").grid(row=0, column=0, sticky="w")
        ttk.Entry(row, textvariable=self.var_hills_csv).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(row, text="…", width=3, command=self._pick_hills_csv).grid(row=0, column=2, sticky="w")
        ttk.Button(row, text="Wczytaj", command=self._load_hills_csv).grid(row=0, column=3, sticky="w", padx=(6,0))

        # ——— Filtr wg kalendarza cyklu ———
        row_cal = ttk.Frame(sec_hill.body); row_cal.grid(row=5, column=0, columnspan=3, sticky="we", pady=(4,0))
        row_cal.columnconfigure(1, weight=1)

        self.var_calendar_csv = tk.StringVar(value="")
        self._calendar_df = None   # pd.DataFrame z wczytanego kalendarza

        ttk.Label(row_cal, text="Kalendarz cyklu:").grid(row=0, column=0, sticky="w")
        ttk.Entry(row_cal, textvariable=self.var_calendar_csv).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(row_cal, text="…", width=3, command=self._pick_calendar_csv).grid(row=0, column=2, sticky="w")
        ttk.Button(row_cal, text="Wczytaj", command=self._load_calendar_csv).grid(row=0, column=3, sticky="w", padx=(4,0))
        ttk.Button(row_cal, text="✕ Wyczyść", command=self._clear_calendar_filter).grid(row=0, column=4, sticky="w", padx=(4,0))

        # ——— Filtr wg tygodnia (wszystkie cykle naraz) ———
        row_week = ttk.Frame(sec_hill.body); row_week.grid(row=6, column=0, columnspan=3, sticky="we", pady=(4,0))
        row_week.columnconfigure(1, weight=1)

        self.var_calendars_dir = tk.StringVar(value="")
        self._all_calendars_df = None   # scalony DataFrame ze wszystkich kalendarzy w folderze

        ttk.Label(row_week, text="Folder kalendarzy:").grid(row=0, column=0, sticky="w")
        ttk.Entry(row_week, textvariable=self.var_calendars_dir).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(row_week, text="…", width=3, command=self._pick_calendars_dir).grid(row=0, column=2, sticky="w")
        ttk.Button(row_week, text="Wczytaj", command=self._load_calendars_dir).grid(row=0, column=3, sticky="w", padx=(4,0))

        row_week2 = ttk.Frame(sec_hill.body); row_week2.grid(row=7, column=0, columnspan=3, sticky="we", pady=(2,0))
        row_week2.columnconfigure(3, weight=1)

        ttk.Label(row_week2, text="Tydzień:").grid(row=0, column=0, sticky="w")
        self.var_week_pick = tk.StringVar()
        self.cbo_week = ttk.Combobox(row_week2, textvariable=self.var_week_pick, state="readonly", width=6)
        self.cbo_week.grid(row=0, column=1, sticky="w", padx=(4,8))
        self.cbo_week.bind("<<ComboboxSelected>>", self._on_week_selected)
        ttk.Button(row_week2, text="◀", width=2, command=self._week_prev).grid(row=0, column=2, sticky="w")
        ttk.Button(row_week2, text="▶", width=2, command=self._week_next).grid(row=0, column=3, sticky="w", padx=(2,8))
        ttk.Button(row_week2, text="✕ Wyczyść", command=self._clear_week_filter).grid(row=0, column=4, sticky="w")

        row_cycle = ttk.Frame(sec_hill.body); row_cycle.grid(row=9, column=0, columnspan=3, sticky="we", pady=(2,0))
        row_cycle.columnconfigure(1, weight=1)
        ttk.Label(row_cycle, text="Cykl:").grid(row=0, column=0, sticky="w")
        self.var_cycle = tk.StringVar()
        _CYCLES = [
            "WC-M","COC-M","FC-M","WC-W","COC-W","FC-W",
            "GP-M","SCOC-M","GP-W","SCOC-W",
            "OG-M","OG-W","WCH-M","WCH-W","SFWC-M","SFWC-W",
            "COCH-EU-M","COCH-EU-W","COCH-AS-M","COCH-AS-W",
            "COCH-NA-M","COCH-NA-W","COCH-SA-M","COCH-SA-W",
            "COCH-AF-M","COCH-AF-W","COCH-OC-M","COCH-OC-W",
            "JWC-M","JWC-W","YOG-M","YOG-W","UNI-M","UNI-W",
            "NKIC-M","NKIC-W","IST-M","IST-W",
        ]
        self.cbo_cycle = ttk.Combobox(row_cycle, textvariable=self.var_cycle,
                                       values=_CYCLES, state="readonly", width=18)
        self.cbo_cycle.grid(row=0, column=1, sticky="w", padx=4)
        def _cycle_prev():
            vals = list(self.cbo_cycle["values"])
            if not vals: return
            cur = self.var_cycle.get()
            idx = vals.index(cur) if cur in vals else 0
            self.var_cycle.set(vals[(idx - 1) % len(vals)])
        def _cycle_next():
            vals = list(self.cbo_cycle["values"])
            if not vals: return
            cur = self.var_cycle.get()
            idx = vals.index(cur) if cur in vals else -1
            self.var_cycle.set(vals[(idx + 1) % len(vals)])
        ttk.Button(row_cycle, text="◀", width=2, command=_cycle_prev).grid(row=0, column=2, sticky="w")
        ttk.Button(row_cycle, text="▶", width=2, command=_cycle_next).grid(row=0, column=3, sticky="w", padx=(2,8))
        ttk.Button(row_cycle, text="▶ Auto-setup", command=self._on_cycle_selected).grid(row=0, column=4, sticky="w")

        row2 = ttk.Frame(sec_hill.body); row2.grid(row=8, column=0, columnspan=3, sticky="we", pady=(4,0))
        row2.columnconfigure(1, weight=1)

        ttk.Label(row2, text="Wybierz skocznię:").grid(row=0, column=0, sticky="w")
        self.var_hill_pick = tk.StringVar()
        self.cbo_hill = ttk.Combobox(row2, textvariable=self.var_hill_pick, state="readonly")
        self.cbo_hill.grid(row=0, column=1, sticky="we", padx=4)
        self.cbo_hill.bind("<<ComboboxSelected>>", self._on_hill_selected)
        ttk.Button(row2, text="◀", width=2, command=self._hill_prev).grid(row=0, column=2, sticky="w")
        ttk.Button(row2, text="▶", width=2, command=self._hill_next).grid(row=0, column=3, sticky="w", padx=(2,0))

        sec_mode = Labeled(left, "Tryb zawodów"); sec_mode.pack(fill=tk.X, pady=(0,8))
        self.var_classic = tk.BooleanVar(value=True)
        self.var_ko50 = tk.BooleanVar(value=False)
        self.var_ko64_full = tk.BooleanVar(value=False)
        def _sync(mode):
            self.var_classic.set(mode=="classic")
            self.var_ko50.set(mode=="ko50")
            self.var_ko64_full.set(mode=="ko64")
        ttk.Radiobutton(sec_mode.body, text="Klasyczny", value=True, variable=self.var_classic,
                        command=lambda:_sync("classic")).grid(row=0,column=0,sticky="w")
        ttk.Radiobutton(sec_mode.body, text="KO 50 (25 par + 5 LL)", value=True, variable=self.var_ko50,
                        command=lambda:_sync("ko50")).grid(row=0,column=1,sticky="w",padx=(10,0))
        ttk.Radiobutton(sec_mode.body, text="KO 64 (pełny turniej 64→1)", value=True, variable=self.var_ko64_full,
                        command=lambda:_sync("ko64")).grid(row=0,column=2,sticky="w",padx=(10,0))

        self.var_round_cuts = tk.StringVar(value="50,30")
        self.var_qual_spots = tk.IntVar(value=50)

        # --- Predefiniowane formaty zawodów ---
        FORMAT_PRESETS = {
            "Classic  (50,30 / Q:50)":   ("50,30",        50),
            "Full  (999,30 / Q:999)":     ("999,30",      999),
            "Mamut  (40,30 / Q:40)":      ("40,30",        40),
            "NKIC  (64,32,16,8,4,2 / Q:64)": ("64,32,16,8,4,2", 64),
        }
        self._format_presets = FORMAT_PRESETS

        def _apply_format_preset(event=None):
            label = self.var_format_preset.get()
            if label in FORMAT_PRESETS:
                cuts, spots = FORMAT_PRESETS[label]
                self.var_round_cuts.set(cuts)
                self.var_qual_spots.set(spots)

        self.var_format_preset = tk.StringVar(value="Classic  (50,30 / Q:50)")
        ttk.Label(sec_mode.body, text="Format").grid(row=1, column=0, sticky="w", pady=(6, 0))
        cbo_format = ttk.Combobox(
            sec_mode.body,
            textvariable=self.var_format_preset,
            values=list(FORMAT_PRESETS.keys()),
            state="readonly",
            width=30,
        )
        cbo_format.grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))
        cbo_format.bind("<<ComboboxSelected>>", _apply_format_preset)

        ttk.Label(sec_mode.body, text="Cięcia rund (—round-cuts)").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(sec_mode.body, textvariable=self.var_round_cuts, width=18).grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Label(sec_mode.body, text="Miejsca z kwalifikacji (—qual-spots)").grid(row=3, column=0, sticky="w")
        ttk.Entry(sec_mode.body, textvariable=self.var_qual_spots, width=10).grid(row=3, column=1, sticky="w")

        sec_wind = Labeled(right, "Wiatr i dynamika"); sec_wind.pack(fill=tk.X, pady=(0,8))
        self.var_wind_mean = tk.DoubleVar(value=0.0)
        self.var_wind_sd = tk.DoubleVar(value=0.8)
        self.var_wind_phi = tk.DoubleVar(value=0.75)
        self.var_wind_takeoff_gain = tk.DoubleVar(value=0.5)
        self.var_wind_flight_gain = tk.DoubleVar(value=2.2)
        grid_entries(sec_wind.body, [
            ("Średni wiatr (—wind-mean)", self.var_wind_mean, float),
            ("Odchylenie (—wind-sd)", self.var_wind_sd, float),
            ("Autokorelacja (—wind-phi)", self.var_wind_phi, float),
            ("Takeoff gain", self.var_wind_takeoff_gain, float),
            ("Flight gain", self.var_wind_flight_gain, float),
        ])

        sec_gate = Labeled(right, "Belka i kompensacje"); sec_gate.pack(fill=tk.X, pady=(0,8))
        self.var_gate = tk.IntVar(value=10)
        self.var_p_gate_change = tk.DoubleVar(value=0.06)
        self.var_max_gate_delta = tk.IntVar(value=2)
        grid_entries(sec_gate.body, [
            ("Belka (—gate)", self.var_gate, int),
            ("Prawd. zmiany (—p-gate-change)", self.var_p_gate_change, float),
            ("Maks. zmiana ± (—max-gate-delta)", self.var_max_gate_delta, int),
        ])

        # --- Losowość i sędziowie ---
        sec_rand = Labeled(right, "Losowość i sędziowie")
        sec_rand.pack(fill=tk.X, pady=(0,8))

        self.var_randomness = tk.DoubleVar(value=1.5)
        self.var_elite_regress = tk.DoubleVar(value=1.5)
        self.var_judges_rho = tk.DoubleVar(value=0.55)

        grid_entries(sec_rand.body, [
            ("Randomness", self.var_randomness, float),
            ("Elite regress", self.var_elite_regress, float),
            ("Korelacja not (—judges-rho)", self.var_judges_rho, float),
        ])

        # --- Podgląd wyników – limity (z Podglądu do Parametrów) ---
        sec_preview_opts = Labeled(right, "Podgląd wyników – limity")
        sec_preview_opts.pack(fill=tk.X, pady=(0,8))

        self.var_prev_qual_n = tk.IntVar(value=50)
        self.var_prev_final_n = tk.IntVar(value=50)
        self.var_prev_qual_all = tk.BooleanVar(value=True)
        self.var_prev_final_all = tk.BooleanVar(value=True)

        row = sec_preview_opts.body
        ttk.Label(row, text="Kwalifikacje: pokaż").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(row, from_=1, to=10000, textvariable=self.var_prev_qual_n, width=6)\
           .grid(row=0, column=1, sticky="w", padx=(4,6))
        ttk.Checkbutton(row, text="Wszystkich", variable=self.var_prev_qual_all)\
           .grid(row=0, column=2, sticky="w")

        ttk.Label(row, text="Konkurs: pokaż").grid(row=1, column=0, sticky="w", pady=(4,0))
        ttk.Spinbox(row, from_=1, to=10000, textvariable=self.var_prev_final_n, width=6)\
           .grid(row=1, column=1, sticky="w", padx=(4,6), pady=(4,0))
        ttk.Checkbutton(row, text="Wszystkich", variable=self.var_prev_final_all)\
           .grid(row=1, column=2, sticky="w", pady=(4,0))

        # bottom – PRZENIESIONY do zakładki "Parametry", żeby nie był ściskany przy embedzie
        bottom = ttk.Frame(self.tab_params)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0,8))
        self.status = tk.StringVar(value="Gotowy.")
        ttk.Label(bottom, textvariable=self.status).pack(side=tk.LEFT)
        self.pbar = ttk.Progressbar(bottom, mode="indeterminate", length=160)
        self.pbar.pack(side=tk.LEFT, padx=8)
        ttk.Button(bottom, text="Uruchom", command=self.run_clicked).pack(side=tk.RIGHT)

        # log — nad paskiem
        sec_log = Labeled(self.tab_params, "Logi")
        sec_log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        self.txt_log = tk.Text(sec_log.body, height=10)
        self.txt_log.pack(fill=tk.BOTH, expand=True)


        # zakładka 'Zawodnicy'
        self._build_roster(self.tab_roster)
        try:
            self._refresh_roster_tab()
        except Exception:
            pass

        # tables
        self._build_preview(self.tab_preview)
        self._build_ko_tabs()

        try:
            self._load_hills_csv()
        except Exception:
            pass

    def _refresh_roster_tab(self):
        # 1) Wczytaj pełny df
        try:
            excel_path = Path(self.var_excel.get())
        except Exception:
            excel_path = None

        try:
            df_full = sim.load_roster(excel_path)
        except Exception as e:
            messagebox.showerror("Błąd wczytywania", f"Nie udało się wczytać bazy zawodników:\n{e}")
            return

        self._roster_df_cache = df_full.copy()

        # 2) Pokaż pełny df w "Baza zawodników"
        if hasattr(self, "db_tree") and self.db_tree:
            try:
                self.db_tree.set_dataframe(df_full)
            except Exception:
                pass

        # 3) Zastosuj filtry z "Wybór skoczków"
        try:
            df_filtered = self._filter_df_by_ui(df_full)
        except Exception:
            df_filtered = df_full

        self._roster_df_filtered = df_filtered.copy()
        
        # 4) Przytnij do 4 kolumn i pokaż w "Zawodnicy"
        basic_cols = [c for c in ["Zawodnik","Kraj","UM","Forma"] if c in df_filtered.columns]
        if not basic_cols:
            basic_cols = list(df_filtered.columns[:4])
        df_basic = df_filtered[basic_cols].copy()

        if hasattr(self, "roster_tree") and self.roster_tree:
            try:
                self.roster_tree.set_dataframe(df_basic)
            except Exception:
                pass

        # 5) Zaktualizuj etykietę pliku w "Baza zawodników"
        try:
            self._db_file_label.configure(text=str(excel_path) if excel_path else "")
        except Exception:
            pass
 
    def _only_basic_roster_cols(self, df):
        cols = [c for c in ["Zawodnik","Kraj","UM","Forma"] if c in df.columns]
        if not cols:
            return df.copy()
        return df[cols].copy()

    def _roster_autosize_columns(self):
        """Ustaw sensowne minimalne szerokości i rozciąganie tylko tam, gdzie trzeba."""
        # lewa tabela
        try:
            tv = self.roster_tree.tree
            cols = list(tv["columns"])
            minw = {"Zawodnik": 220, "Kraj": 60, "UM": 42, "Forma": 56}
            for c in cols:
                w = minw.get(c, 80)
                tv.column(c, width=w, minwidth=w, stretch=(c == "Zawodnik"))
        except Exception:
            pass

        # prawa tabela (startlista)
        try:
            tv = self.startlist.tv_main
            cols = list(tv["columns"])
            # węższe „Nr” + centrowanie
            for c in cols:
                if c == "Nr":
                    tv.column(c, width=36, minwidth=32, stretch=False, anchor=tk.CENTER)
                elif c == "Zawodnik":
                    tv.column(c, width=240, minwidth=200, stretch=True)
                else:
                    tv.column(c, width=60, minwidth=56, stretch=False)
        except Exception:
            pass

    def _force_nr_width(self):
        """Wymuś wąską kolumnę Nr w zamrożonej części startlisty (także jeśli coś ją poszerzyło)."""
        try:
            tvf = self.startlist.tv_fixed
            fcols = list(tvf["columns"])
            if fcols:
                tvf.column(fcols[0], width=36, minwidth=32, stretch=False, anchor=tk.CENTER)
                if hasattr(self.startlist, "_lock_fixed_width"):
                    self.startlist._lock_fixed_width(46)
        except Exception:
            pass

    def _build_roster(self, parent):
        """Zakładka 'Zawodnicy' – PanedWindow: lewa (baza+przyciski), prawa (lista startowa)."""
        
        if not hasattr(self, "selected_df"):
            self.selected_df = pd.DataFrame()

        # 2 panele z suwakiem pośrodku
        pw = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ===== LEWY PANEL (baza + przyciski) =====
        left_pane = ttk.Frame(pw)
        pw.add(left_pane, weight=1)

        # siatka: 2 kolumny (tabela, przyciski) / 2 wiersze (nagłówek, reszta)
        left_pane.columnconfigure(0, weight=1, uniform="roster")
        left_pane.columnconfigure(1, weight=0)
        left_pane.rowconfigure(1, weight=0)   # pasek narzędzi
        left_pane.rowconfigure(2, weight=1)   # tabela rośnie

        # nagłówek dla lewej kolumny
        head_left = Labeled(left_pane, "Baza zawodników (z pliku)")
        head_left.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0,6), pady=(0,6))

        # pasek narzędzi (odśwież + źródło)
        tools_left = ttk.Frame(left_pane)
        tools_left.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0,6), pady=(0,6))
        ttk.Button(tools_left, text="Odśwież z pliku", command=self._refresh_roster_tab).pack(side=tk.LEFT)
        ttk.Label(tools_left, text="Źródło:").pack(side=tk.LEFT, padx=(10,2))
        try:
            ttk.Label(tools_left, textvariable=self.var_excel).pack(side=tk.LEFT)
        except Exception:
            pass

        # tabela lewa (baza)
        self.roster_tree = Table(left_pane)
        try:
            self.roster_tree.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        except Exception:
            pass
        self.roster_tree.grid(row=2, column=0, sticky="nsew", padx=(0,6))

        # kolumna przycisków – stała szerokość, nie rozciąga się
        btns = ttk.Frame(left_pane)
        btns.grid(row=2, column=1, sticky="ns")
        for txt, cmd in (
            ("Dodaj →", self._roster_add_selected),
            ("← Usuń", self._roster_remove_selected),
        ):
            ttk.Button(btns, text=txt, command=cmd).pack(fill=tk.X, pady=2)
        ttk.Separator(btns, orient="horizontal").pack(fill=tk.X, pady=6)
        ttk.Button(btns, text="Dodaj wszystkich →", command=self._on_add_all).pack(fill=tk.X, pady=(8,2))
        ttk.Button(btns, text="← Usuń wszystkich", command=self._roster_remove_all).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="↑ Góra", command=lambda: self._roster_move_selected(-1)).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="↓ Dół", command=lambda: self._roster_move_selected(+1)).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="Wyczyść", command=self._roster_clear_selected).pack(fill=tk.X, pady=(8,2))

        try:
            self.roster_tree.tree.bind("<Double-1>", lambda e: self._roster_add_selected())
        except Exception:
            pass

        # ===== PRAWY PANEL (lista startowa) =====
        right_pane = ttk.Frame(pw)
        pw.add(right_pane, weight=1)

        right_pane.columnconfigure(0, weight=1, uniform="roster")
        right_pane.rowconfigure(1, weight=1)

        head_right = Labeled(right_pane, "Lista startowa (Twoi wybrani – kolejność)")
        head_right.grid(row=0, column=0, sticky="ew", padx=(6,0), pady=(0,6))
        # ===== PRAWY PANEL (lista startowa) =====
        right_pane = ttk.Frame(pw)
        pw.add(right_pane, weight=1)

        right_pane.columnconfigure(0, weight=1, uniform="roster")
        right_pane.rowconfigure(1, weight=1)

        head_right = Labeled(right_pane, "Lista startowa (Twoi wybrani – kolejność)")
        head_right.grid(row=0, column=0, sticky="ew", padx=(6,0), pady=(0,6))

        # --- [NOWE] Toolbar: wybór obiegu + ustaw wg klasyfikacji (odwrotnie)
        toolbar = ttk.Frame(head_right.body)
        toolbar.pack(fill="x", padx=6, pady=(2,4))

        ttk.Label(toolbar, text="Klasyfikacja:").pack(side="left")
        self.var_gc_cycle = tk.StringVar(value="")
        self.gc_cycle_cb = ttk.Combobox(toolbar, textvariable=self.var_gc_cycle, width=12, state="readonly")
        try:
            self.gc_cycle_cb["values"] = self._gc_available_cycles()
            if self.gc_cycle_cb["values"]:
                self.gc_cycle_cb.current(0)
        except Exception:
            self.gc_cycle_cb["values"] = []
        self.gc_cycle_cb.pack(side="left", padx=(6,8))

        ttk.Button(toolbar,
                text="Ustaw wg klasyfikacji (odwrotnie)",
                command=self._on_apply_gc_reverse).pack(side="left")

        # --- tabela listy startowej jak dotąd
        self.startlist = FrozenFirstColTable(right_pane, frozen_col="Nr")
        try:
            self.startlist.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        except Exception:
            pass
        self.startlist.grid(row=1, column=0, sticky="nsew", padx=(6,0))


        self.startlist = FrozenFirstColTable(right_pane, frozen_col="Nr")
        try:
            self.startlist.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        except Exception:
            pass
        self.startlist.grid(row=1, column=0, sticky="nsew", padx=(6,0))

        try:
            self.startlist.tv_main.bind("<Double-1>", lambda e: self._roster_remove_selected())
        except Exception:
            pass

        # ustaw startową pozycję suwaka ~ 50/50 po wyrenderowaniu
        self.after(150, lambda: pw.sashpos(0, max(200, int(pw.winfo_width() * 0.5))))
        # lekkie auto-szerokości kolumn (po pierwszym wczytaniu)
        self.after(200, self._roster_autosize_columns)

    def _refresh_startlist_view(self):
        """Odśwież prawą tabelę zgodnie z self.selected_df."""
        
        if not hasattr(self, "selected_df"):
            self.selected_df = pd.DataFrame()
        df = self.selected_df.copy()
        if not df.empty:
            # zapewnij poprawne numery startowe
            df = df.copy()
            df["Nr"] = range(1, len(df) + 1)
            cols = ["Nr"] + [c for c in df.columns if c != "Nr"]
            df = df[cols]
        try:
            self.startlist.set_dataframe(df)
        except Exception:
            pass

        self.after(10, self._roster_autosize_columns)
        # po re-renderze wymuś wąski Nr (kilka razy – na wypadek asynchronicznych auto-dopasowań)
        for delay in (0, 30, 120):
            try:
                self.after(delay, self._force_nr_width)
            except Exception:
                pass
     
    @staticmethod
    def _convert_numeric_strict(series):
        
        """Spróbuj zrzutować całą kolumnę do liczby. Jeśli się nie da – zostaw jak jest."""
        if is_numeric_dtype(series):
            return series
        try:
            return pd.to_numeric(series)
        except Exception:
            return series

    def _tree_selection_to_df(self, tree_widget, name_col="Zawodnik"):
        """Zamień zaznaczone wiersze z lewej (Table.tree) na DataFrame w oparciu o widoczne kolumny."""
        
        iids = list(getattr(tree_widget, "selection")())
        if not iids:
            return pd.DataFrame()
        cols = list(tree_widget["columns"])  # np. ["Kraj", "UM", "Forma", ...]
        rows = []
        for iid in iids:
            item = tree_widget.item(iid)
            row = {name_col: str(item.get("text", "")).strip()}
            values = list(item.get("values", []))
            # jeśli name_col jest w kolumnach po prawej, preferuj jego wartość zamiast text (#0)
            try:
                if name_col in cols:
                    idx = cols.index(name_col)
                    if idx < len(values) and not row.get(name_col):
                        row[name_col] = values[idx]
            except Exception:
                pass
            for c, v in zip(cols, values):
                row[str(c)] = v
            rows.append(row)
        df = pd.DataFrame(rows)
        # łagodne rzutowanie liczb
        for c in df.columns:
            df[c] = self._convert_numeric_strict(df[c])
        return df

    def _gc_available_cycles(self):
        """
        Zwróć listę obiegów, dla których mamy wczytaną klasyfikację IND (players).
        Gdy jeszcze nie ma zakładki Klasyfikacje/CSV – używa listy domyślnej.
        """
        # Spróbuj wyczytać z Klasyfikacji, jeśli już zbudowane/załadowane:
        try:
            tab = getattr(self, "tab_klasyfikacje", None)
            sheet_data = getattr(tab, "sheet_data", None)
            if isinstance(sheet_data, dict):
                out = []
                for key, bundle in sheet_data.items():
                    try:
                        dfp = (bundle or {}).get("players", None)
                        if dfp is not None and hasattr(dfp, "empty") and not dfp.empty:
                            out.append(str(key))
                    except Exception:
                        pass
                if out:
                    return sorted(out)
        except Exception:
            pass

        # Fallback – pełna lista znanych obiegów (M/W + JUN):
        return [
            # SENIOR
            "WC-M","WC-W","COC-M","COC-W","FC-M","FC-W","GP-M","GP-W","SCOC-M","SCOC-W",
            # JUNIOR
            "JC-M","JC-W","MC-M","MC-W","PC-M","PC-W","QC-M","QC-W","TC-M","TC-W",
            "AC-M","AC-W","BC-M","BC-W","DC-M","DC-W",
        ]

    def _on_apply_gc_reverse(self):
        """
        Ustaw kolejność 'selected_df' wg odwrotnej kolejności klasyfikacji generalnej
        wybranego obiegu (combobox obok przycisku).
        Zasady:
        - Zawodnicy nieobecni w rankingu → na początku (zachowując dotychczasowy porządek).
        - Zawodnicy z rankingu → od najgorszego do lidera (czyli „odwrotnie” do klasyfikacji).
        """
        if not hasattr(self, "selected_df") or self.selected_df is None or self.selected_df.empty:
            try: messagebox.showinfo("Lista startowa", "Najpierw dodaj zawodników do listy startowej.")
            except Exception: pass
            return

        tag = (self.var_gc_cycle.get() or "").strip()
        if not tag:
            try: messagebox.showwarning("Klasyfikacja", "Wybierz obieg (np. WC-M) obok przycisku.")
            except Exception: pass
            return

        # Pobierz tabelę klasyfikacji IND dla obiegu
        df_rank = None
        try:
            tab = getattr(self, "tab_klasyfikacje", None)
            bundle = getattr(tab, "sheet_data", {}).get(tag, {})
            df_rank = bundle.get("players")
        except Exception:
            df_rank = None

        # Ostrożna normalizacja kolumn
        def _std_players_df(dfp):
            if dfp is None or getattr(dfp, "empty", True):
                return None
            dfp = dfp.copy()
            # spróbuj znaleźć kolumny 'JUMPER' i 'PTS'
            cols = {c.upper(): c for c in dfp.columns}
            name_col = cols.get("JUMPER", cols.get("ZAWODNIK", None))
            pts_col  = cols.get("PTS", cols.get("PUNKTY", None))
            if not name_col:
                # brak nazw – nic nie zrobimy
                return None
            # posortuj rosnąco po pozycji (jeżeli mamy PTS to malejąco, ale indeks pozycji i tak wyznaczamy enumerate)
            if pts_col and pts_col in dfp.columns:
                try:
                    dfp = dfp.sort_values(pts_col, ascending=False, kind="stable")
                except Exception:
                    pass
            # zostaw samą kolumnę z nazwiskami w kolejności klasyfikacji (0 = lider)
            return pd.DataFrame({"JUMPER": dfp[name_col].astype(str).tolist()})

        dfp = _std_players_df(df_rank)
        if dfp is None or dfp.empty:
            # Spróbuj fallbacku (CSV jeszcze nie wczytane) – pokaż komunikat
            try: messagebox.showwarning("Klasyfikacja", f"Brak tabeli zawodników dla {tag}.")
            except Exception: pass
            return

        # Mapa: nazwisko -> pozycja w GC (0 = lider)
        order = [str(x).strip() for x in dfp["JUMPER"].astype(str).tolist()]
        pos = {name: i for i, name in enumerate(order)}

        df = self.selected_df.copy()
        if "Zawodnik" not in df.columns:
            try: messagebox.showerror("Lista startowa", "Nie widzę kolumny 'Zawodnik' w liście startowej.")
            except Exception: pass
            return

        def _norm(s): return str(s).strip()
        df["_has_rank"] = df["Zawodnik"].astype(str).map(lambda x: 1 if _norm(x) in pos else 0)
        df["_pos"]      = df["Zawodnik"].astype(str).map(lambda x: pos.get(_norm(x), -1))

        # sort: najpierw bez rankingu (0), potem z rankingiem (1) – w grupie rankingowej od najgorszego do najlepszego
        # czyli _has_rank rosnąco, a _pos malejąco
        df = df.sort_values(by=["_has_rank","_pos"], ascending=[True, False], kind="stable").drop(columns=["_has_rank","_pos"])
        self.selected_df = df.reset_index(drop=True)
        self._refresh_startlist_view()

    def _roster_add_selected(self):
        """Dodaj zaznaczonych z lewej do listy startowej (bez duplikatów)."""
        
        if not hasattr(self, "selected_df"):
            self.selected_df = pd.DataFrame()

        # pobierz zaznaczenie z lewej
        try:
            left_df = self._tree_selection_to_df(self.roster_tree.tree, name_col=getattr(self.roster_tree, "_name_col", "Zawodnik"))
        except Exception:
            left_df = pd.DataFrame()
        if left_df.empty:
            return

        # usuń duplikaty wg (Zawodnik, Kraj)
        for col in ("Zawodnik", "Kraj"):
            if col not in left_df.columns and hasattr(self, "_roster_df_cache") and col in getattr(self, "_roster_df_cache").columns:
                # dopełnij brakujące kolumny z cache, jeśli trzeba
                left_df[col] = ""

        key_cols = [c for c in ["Zawodnik", "Kraj"] if c in left_df.columns]
        if not key_cols:
            key_cols = ["Zawodnik"]

        # dołącz do selected_df, eliminując istniejące
        if self.selected_df.empty:
            base = pd.DataFrame(columns=[*left_df.columns])
        else:
            base = self.selected_df.copy()
            # ujednolicenie kolumn
            for c in left_df.columns:
                if c not in base.columns:
                    base[c] = ""
            for c in base.columns:
                if c not in left_df.columns:
                    left_df[c] = ""

        if base.empty:
            merged = left_df.copy()
        else:
            # dodaj tylko te, których nie ma już w bazie
            existing_keys = set(tuple(x) for x in base[key_cols].astype(str).to_records(index=False))
            to_add = left_df[~left_df[key_cols].astype(str).apply(tuple, axis=1).isin(existing_keys)]
            merged = pd.concat([base, to_add], ignore_index=True)

        # ustaw kolejność (Nr) i zapisz
        merged = merged.reset_index(drop=True)
        self.selected_df = merged
        self._refresh_startlist_view()

    def _startlist_get_selected_index(self):
        """Zwróć indeks (0-based) zaznaczonego wiersza po prawej, albo None."""
        try:
            sel = self.startlist.tv_main.selection()
            if not sel:
                return None
            return self.startlist.tv_main.index(sel[0])
        except Exception:
            return None

    def _roster_remove_selected(self):
        """Usuń wskazanego (po prawej) z listy startowej."""
        
        if getattr(self, "selected_df", None) is None or self.selected_df.empty:
            return
        idx = self._startlist_get_selected_index()
        if idx is None:
            return
        self.selected_df = self.selected_df.drop(self.selected_df.index[idx]).reset_index(drop=True)
        self._refresh_startlist_view()

    def _roster_move_selected(self, delta: int):
        """Przesuń zaznaczonego (po prawej) o delta pozycji (−1 w górę, +1 w dół)."""
        if getattr(self, "selected_df", None) is None or self.selected_df.empty:
            return
        idx = self._startlist_get_selected_index()
        if idx is None:
            return
        new_idx = max(0, min(len(self.selected_df) - 1, idx + delta))
        if new_idx == idx:
            return
        df = self.selected_df.copy()
        row = df.iloc[idx].copy()
        df = df.drop(df.index[idx])
        df = pd.concat([df.iloc[:new_idx], row.to_frame().T, df.iloc[new_idx:]], ignore_index=True)
        self.selected_df = df.reset_index(drop=True)
        self._refresh_startlist_view()
        # odtwórz zaznaczenie po przestawieniu
        try:
            self.startlist.tv_main.selection_set(self.startlist.tv_main.get_children()[new_idx])
            self.startlist.tv_main.see(self.startlist.tv_main.get_children()[new_idx])
        except Exception:
            pass

    def _roster_clear_selected(self):
        """Wyczyść listę startową (prawa tabela)."""
        
        self.selected_df = pd.DataFrame()
        self._refresh_startlist_view()

    def _add_players_to_startlist(self, df_new):
        """Dołącz zawodników (Zawodnik/Kraj/UM/Forma) do Listy startowej z deduplikacją."""
        
        if df_new is None:
            return
        if df_new.empty:
            self.log("[WYBÓR] Brak zaznaczenia do przeniesienia.")
            return

        # tylko podstawowe kolumny (jeśli są)
        keep = [c for c in ["Zawodnik", "Kraj", "UM", "Forma"] if c in df_new.columns] or list(df_new.columns[:4])
        df_new = df_new[keep].copy()

        # klucze do deduplikacji
        for c in ("Zawodnik", "Kraj"):
            if c not in df_new.columns:
                df_new[c] = ""

        # baza docelowa
        if not hasattr(self, "selected_df") or self.selected_df is None:
            base = pd.DataFrame(columns=keep)
        else:
            base = self.selected_df.copy()
            for c in keep:
                if c not in base.columns:
                    base[c] = ""

        key = [c for c in ("Zawodnik", "Kraj") if c in df_new.columns and c in base.columns] or ["Zawodnik"]
        exist = set(tuple(x) for x in base[key].astype(str).to_records(index=False))
        to_add = df_new[~df_new[key].astype(str).apply(tuple, axis=1).isin(exist)]

        self.selected_df = pd.concat([base[keep], to_add[keep]], ignore_index=True)
        self._refresh_startlist_view()
        self.log(f"[WYBÓR] Dodano {len(to_add)} z {len(df_new)} pozycji do Listy startowej")

    def _on_add_all(self):
        

        # źródło = to co widać po lewej (po filtrach)
        df_src = getattr(self, "_roster_df_filtered", None)
        if df_src is None or df_src.empty:
            return

        # tylko 4 kolumny jak w lewej tabeli
        basic_cols = [c for c in ["Zawodnik", "Kraj", "UM", "Forma"] if c in df_src.columns]
        if not basic_cols:
            basic_cols = list(df_src.columns[:4])
        df_src = df_src[basic_cols].copy()

        # upewnij się, że są klucze do deduplikacji
        for c in ("Zawodnik", "Kraj"):
            if c not in df_src.columns:
                df_src[c] = ""

        # baza docelowa
        if not hasattr(self, "selected_df") or self.selected_df is None:
            self.selected_df = pd.DataFrame(columns=basic_cols)
        base = self.selected_df.copy()
        for c in basic_cols:
            if c not in base.columns:
                base[c] = ""

        # dodaj tylko tych, których jeszcze nie ma (po Zawodnik+Kraj)
        key_cols = [c for c in ["Zawodnik", "Kraj"] if c in base.columns and c in df_src.columns]
        if not key_cols:
            key_cols = ["Zawodnik"]
        existing = set(tuple(x) for x in base[key_cols].astype(str).to_records(index=False))
        to_add = df_src[~df_src[key_cols].astype(str).apply(tuple, axis=1).isin(existing)]

        self.selected_df = pd.concat([base[basic_cols], to_add[basic_cols]], ignore_index=True)

        # odśwież prawą tabelę (Nr zostanie nadany w _refresh_startlist_view)
        self._refresh_startlist_view()

    def _roster_remove_all(self):
        """Usuń wszystkich z listy startowej (to samo co 'Wyczyść')."""
        self._roster_clear_selected()

    def _roster_autosize_columns(self):
        # lewa tabela (baza)
        try:
            tv = self.roster_tree.tree
            cols = list(tv["columns"])
            minw = {"Zawodnik": 220, "Kraj": 60, "UM": 42, "Forma": 56}
            for c in cols:
                w = minw.get(c, 80)
                tv.column(c, width=w, minwidth=w, stretch=(c == "Zawodnik"))
        except Exception:
            pass

        # prawa tabela (startlista) – część główna
        try:
            tv = self.startlist.tv_main
            cols = list(tv["columns"])
            for c in cols:
                if c == "Zawodnik":
                    tv.column(c, width=240, minwidth=200, stretch=True)
                else:
                    tv.column(c, width=60, minwidth=56, stretch=False)
        except Exception:
            pass

        # prawa tabela (startlista) – zamrożona kolumna "Nr"
        try:
            tvf = self.startlist.tv_fixed
            fcols = list(tvf["columns"])
            if fcols:
                tvf.column(fcols[0], width=36, minwidth=32, anchor=tk.CENTER, stretch=False)
        except Exception:
            pass

    def _build_db_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=6, pady=6)

        ttk.Label(top, text="Plik z bazą:").pack(side="left")
        excel_path_str = ""
        try:
            excel_path_str = self.var_excel.get()
        except Exception:
            pass
        self._db_file_label = ttk.Label(top, text=excel_path_str, foreground="#666")
        self._db_file_label.pack(side="left", padx=(6, 12))

        ttk.Button(top, text="Odśwież z pliku", command=self._refresh_roster_tab).pack(side="left")

        table_frame = ttk.Frame(parent)
        table_frame.pack(fill="both", expand=True, padx=6, pady=(0,6))

        # Użyj tej samej klasy tabeli co w innych kartach (np. Table/DataTable)
        self.db_tree = Table(table_frame)
        self.db_tree.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        self.db_tree.pack(fill="both", expand=True)

    def _build_filter_tab(self, parent):

        # ===== GÓRNY RZĄD KONTROLEK =====
        wrap = ttk.Frame(parent); wrap.pack(fill="x", padx=8, pady=8)

        # a) Płeć
        ttk.Label(wrap, text="Płeć:").grid(row=0, column=0, sticky="w", padx=(0,6))
        self.var_f_gender = tk.StringVar(value="WSZYSCY")  # WSZYSCY / M / W
        gender_cb = ttk.Combobox(wrap, width=10, textvariable=self.var_f_gender, values=["WSZYSCY","M","W"], state="readonly")
        gender_cb.grid(row=0, column=1, sticky="w", padx=(0,12))

        # b) JUN/SEN
        ttk.Label(wrap, text="JUN/SEN:").grid(row=0, column=2, sticky="w", padx=(0,6))
        self.var_f_level = tk.StringVar(value="WSZYSCY")  # WSZYSCY / JUN / SEN
        level_cb = ttk.Combobox(wrap, width=10, textvariable=self.var_f_level, values=["WSZYSCY","JUN","SEN"], state="readonly")
        level_cb.grid(row=0, column=3, sticky="w", padx=(0,12))

        # c) Kraj (kody rozdzielone przecinkami, np. "POL, AUT, SLO")
        ttk.Label(wrap, text="Kraj(e):").grid(row=0, column=4, sticky="w", padx=(0,6))
        self.var_f_countries = tk.StringVar(value="")
        ttk.Entry(wrap, textvariable=self.var_f_countries, width=24).grid(row=0, column=5, sticky="w", padx=(0,12))

        # d) Wiek (min-max)
        ttk.Label(wrap, text="Wiek:").grid(row=0, column=6, sticky="w", padx=(0,6))
        self.var_f_age_min = tk.StringVar(value="")
        self.var_f_age_max = tk.StringVar(value="")
        ttk.Entry(wrap, width=5, textvariable=self.var_f_age_min).grid(row=0, column=7, sticky="w")
        ttk.Label(wrap, text="–").grid(row=0, column=8, sticky="w", padx=4)
        ttk.Entry(wrap, width=5, textvariable=self.var_f_age_max).grid(row=0, column=9, sticky="w", padx=(0,12))

        # e) UM / Forma (min)
        ttk.Label(wrap, text="UM ≥").grid(row=1, column=0, sticky="w", padx=(0,6), pady=(8,0))
        self.var_f_um_min = tk.StringVar(value="")
        ttk.Entry(wrap, width=5, textvariable=self.var_f_um_min).grid(row=1, column=1, sticky="w", pady=(8,0))

        ttk.Label(wrap, text="Forma ≥").grid(row=1, column=2, sticky="w", padx=(12,6), pady=(8,0))
        self.var_f_forma_min = tk.StringVar(value="")
        ttk.Entry(wrap, width=5, textvariable=self.var_f_forma_min).grid(row=1, column=3, sticky="w", pady=(8,0))

        # f) Tylko z prawem startu / tylko zdrowi
        self.var_f_ps_only = tk.BooleanVar(value=False)
        self.var_f_healthy_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(wrap, text="Tylko z prawem startu (PrawoStartu ≥ 1)", variable=self.var_f_ps_only).grid(row=1, column=4, columnspan=2, sticky="w", padx=(0,12), pady=(8,0))
        ttk.Checkbutton(wrap, text="Tylko zdrowi (Kontuzja == 0)", variable=self.var_f_healthy_only).grid(row=1, column=6, columnspan=3, sticky="w", pady=(8,0))

        # g) Szukaj w nazwisku
        ttk.Label(wrap, text="Szukaj:").grid(row=2, column=0, sticky="w", padx=(0,6), pady=(8,0))
        self.var_f_search = tk.StringVar(value="")
        ttk.Entry(wrap, textvariable=self.var_f_search, width=24).grid(row=2, column=1, columnspan=3, sticky="w", pady=(8,0))

        # i) Zawody / Prawo Startu
        ttk.Label(wrap, text="Zawody (Prawo Startu):").grid(row=3, column=0, sticky="w", padx=(0,6), pady=(8,0))
        self.var_f_comp = tk.StringVar(value="WSZYSCY")
        ttk.Combobox(
            wrap, width=14, textvariable=self.var_f_comp,
            values=["WSZYSCY","WC","COC","FC","GP","SCOC","JUN"], state="readonly"
        ).grid(row=3, column=1, sticky="w", pady=(8,0))

        self.var_f_use_ps_rules = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            wrap, text="Uwzględniaj zasady (wiek + czas trwania)",
            variable=self.var_f_use_ps_rules
        ).grid(row=3, column=2, columnspan=3, sticky="w", padx=(12,0), pady=(8,0))

        ttk.Label(wrap, text="Sezon ref. (np. 2025/26):").grid(row=3, column=5, sticky="w", padx=(12,6), pady=(8,0))
        self.var_f_ref_season = tk.StringVar(value="")
        ttk.Entry(wrap, textvariable=self.var_f_ref_season, width=12)\
            .grid(row=3, column=6, sticky="w", pady=(8,0))

        # h) Przyciski
        btns = ttk.Frame(parent); btns.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(btns, text="Zastosuj filtry", command=self._refresh_roster_tab).pack(side="left")
        ttk.Button(btns, text="Wyczyść", command=self._clear_filters).pack(side="left", padx=(8,0))

        # podpowiedź
        hint = ttk.Label(parent, text="Uwaga: filtrowana lista pojawia się w zakładce „Zawodnicy”.", foreground="#666")
        hint.pack(fill="x", padx=8, pady=(0,8))

    def _build_quotas_tab(self, parent):
        if not hasattr(self, "quota_tables"):
            self.quota_tables = {}
        # --- rejestry widżetów (muszą istnieć zanim zaczniemy dodawać tabele) ---
        # WYBÓR (dwie listy na płeć: kraje i zawodnicy)
        self._wybor_countries = getattr(self, "_wybor_countries", {})
        self._wybor_players   = getattr(self, "_wybor_players", {})
        if not isinstance(self._wybor_countries, dict): self._wybor_countries = {}
        if not isinstance(self._wybor_players, dict):   self._wybor_players   = {}

        # KWOTY (osobne rejestry, żeby odświeżanie WYBÓR ich nie dotykało)
        self._kwoty_countries = getattr(self, "_kwoty_countries", {})
        self._kwoty_players   = getattr(self, "_kwoty_players", {})
        if not isinstance(self._kwoty_countries, dict): self._kwoty_countries = {}
        if not isinstance(self._kwoty_players, dict):   self._kwoty_players   = {}
        """
        Zakładka 'Kwoty Startowe' z podzakładkami MEN, WOMEN, JUN.
        MEN:  WC-M, COC-M, FC-M
        WOMEN: WC-W, COC-W, FC-W
        JUN:   puste – do uzupełnienia później
        """
        self._kwoty_countries = getattr(self, "_kwoty_countries", {})
        self._kwoty_players   = getattr(self, "_kwoty_players", {})
        self._wyborCOCH_countries = {}
        self._wyborCOCH_players = {}

        # ——— fallback: jeśli nie masz helpera Labeled, użyj LabelFrame ———
        try:
            Labeled  # noqa: F401
        except NameError:
            class Labeled(ttk.LabelFrame):  # type: ignore
                def __init__(self, parent, title):
                    super().__init__(parent, text=title)
                    self.body = self

        # ——— domyślne dane wg grafiki ———
        def _df_wc():
            pos = list(range(1, 15)) + ["Pozostali"]
            cnt = [7, 6, 6, 5, 5, 4, 4, 4, 3, 3, 3, 2, 2, 2, 1]
            return pd.DataFrame({"Pozycja": pos, "Ilość": cnt})

        def _df_coc():
            pos = list(range(1, 17)) + ["Pozostali"]
            cnt = [7, 6, 6, 6, 5, 5, 5, 4, 4, 4, 3, 3, 3, 2, 2, 2, 1]
            return pd.DataFrame({"Pozycja": pos, "Ilość": cnt})

        def _df_fc():
            pos = list(range(1, 19)) + ["Pozostali z pkt", "Pozostali"]
            cnt = [7, 7, 6, 6, 6, 5, 5, 5, 5, 5, 4, 4, 4, 4, 3, 3, 3, 3, 2, 1]
            return pd.DataFrame({"Pozycja": pos, "Ilość": cnt})
        
        def _df_gp_summer():
            # 1..12 + "Pozostali" z Twoją mapą: 6,5,5,4,4,4,3,3,3,2,2,2,1
            pos = list(range(1, 13)) + ["Pozostali"]
            qty = [6, 5, 5, 4, 4, 4, 3, 3, 3, 2, 2, 2, 1]
            return pd.DataFrame({"Pozycja": pos, "Ilość": qty})

        def _df_scoc_summer():
            # identyczna siatka jak GP wg Twojej specyfikacji
            pos = list(range(1, 13)) + ["Pozostali"]
            qty = [6, 5, 5, 4, 4, 4, 3, 3, 3, 2, 2, 2, 1]
            return pd.DataFrame({"Pozycja": pos, "Ilość": qty})
        
        # --- JUN: domyślna tabela (1..16 + "Pozostali") ---
        def _df_jun():
            pos = list(range(1, 17)) + ["Pozostali"]
            qty = [2]*16 + [1]
            return pd.DataFrame({"Pozycja": pos, "Ilość": qty})

        # --- rysowanie jednego boxa w siatce (row, col) ---
        def _build_one_at(grid, row, col, key_title, df):
            # key_title = np. "JC-M" / "QC-W" (użyjemy jako tytułu i klucza)
            box = Labeled(grid, key_title)
            box.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            t = Table(box.body)
            # flagi w kolumnie "Pozycja"
            t.enable_flags(getattr(self.tab_klasyfikacje, "flag_dir", "./flags"), flag_col="Pozycja")
            t.pack(fill=tk.BOTH, expand=True)
            t.set_dataframe(df[["Pozycja", "Ilość"]].copy())
            try:
                tv = t.tree
                tv.column("Pozycja", width=160, minwidth=120, stretch=True)
                tv.column("Ilość",   width=70,  minwidth=60,  stretch=False, anchor="center")
            except Exception:
                pass
            self.quota_tables[key_title] = t  # zapisz referencję do późniejszych podmian

        # --- JUN: box 1 kolumna ("Kraj"), bez "Ilość" i bez Lp. ---
        def _build_one_at_jun_onecol(grid, row, col, key_title, df):
            box = Labeled(grid, key_title)
            box.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            t = Table(box.body)

            # Flagi czytamy teraz z kolumny "Kraj"
            try:
                df1 = df[["Pozycja"]].copy().rename(columns={"Pozycja": "Kraj"})
            except Exception:
                df1 = df.copy()
                if "Pozycja" in df1.columns:
                    df1 = df1.rename(columns={"Pozycja": "Kraj"})

            # ważne: flag_col="Kraj"
            t.enable_flags(getattr(self.tab_klasyfikacje, "flag_dir", "./flags"), flag_col="Kraj")
            t.pack(fill=tk.BOTH, expand=True)
            t.set_dataframe(df1)

            try:
                tv = t.tree
                tv.heading("Kraj", text="Kraj")
                tv.column("Kraj", width=200, minwidth=140, stretch=True, anchor="w")
            except Exception:
                pass

            self.quota_tables[key_title] = t

        # ——— notebook z podzakładkami MEN/WOMEN/JUN ———
        # 1) GÓRNY notebook
        sub = ttk.Notebook(parent)          # jak u Ciebie
        sub.pack(fill="both", expand=True)

        # 2) Grupy
        tab_overview = ttk.Frame(sub)
        tab_kadry    = ttk.Frame(sub)
        tab_kwotygrp = ttk.Frame(sub)
        tab_wyborgrp = ttk.Frame(sub)

        sub.add(tab_overview, text="Przegląd")
        sub.add(tab_kadry,    text="Kadry")
        sub.add(tab_kwotygrp, text="Kwoty")
        sub.add(tab_wyborgrp, text="Wybór")

        # 3) Wewnętrzne notebooki (MUSZĄ powstać przed tworzeniem tab_* niżej)
        nb_kadry = ttk.Notebook(tab_kadry);         nb_kadry.pack(fill="both", expand=True)
        nb_kwoty = ttk.Notebook(tab_kwotygrp);      nb_kwoty.pack(fill="both", expand=True)
        nb_wybor = ttk.Notebook(tab_wyborgrp);      nb_wybor.pack(fill="both", expand=True)
        self._nb_wybor = nb_wybor
        self._nb_kwoty = nb_kwoty
        self._nb_kwoty_sub = sub  # górny notebook (Przegląd/Kadry/Kwoty/Wybór)

        # 4) TWÓRZ POSZCZEGÓLNE RAMKI Z WŁAŚCIWYM RODZICEM (to był błąd)
        tab_select     = ttk.Frame(tab_overview)

        tab_men        = ttk.Frame(nb_kadry)
        tab_women      = ttk.Frame(nb_kadry)
        tab_lato       = ttk.Frame(nb_kadry)
        tab_jun_m      = ttk.Frame(nb_kadry)
        tab_jun_w      = ttk.Frame(nb_kadry)

        tab_kwoty      = ttk.Frame(nb_kwoty)
        tab_kwoty_lato = ttk.Frame(nb_kwoty)
        tab_rights     = ttk.Frame(nb_kwoty)

        tab_wybor_m    = ttk.Frame(nb_wybor)
        tab_wybor_w    = ttk.Frame(nb_wybor)
        tab_wybor_lato = ttk.Frame(nb_wybor)
        tab_wybor_jun  = ttk.Frame(nb_wybor)
        tab_wybor_ch   = ttk.Frame(nb_wybor)
        tab_wybor_jwc  = ttk.Frame(nb_wybor)
        tab_wybor_uni  = ttk.Frame(nb_wybor)
        tab_wybor_yog  = ttk.Frame(nb_wybor)
        tab_wybor_coch = ttk.Frame(nb_wybor)

        # 5) Rejestracja w notebookach (tu już NIC nie pakujesz/gridujesz – Notebook zarządza)
        # Przegląd
        # (jeśli masz przyciski itp. – budujesz je wewnątrz tab_select)
        # nie sub.add, tylko wewnątrz 'Przegląd' masz jedną ramkę
        # i tam budujesz UI. Nic więcej nie trzeba.

        # Kadry
        nb_kadry.add(tab_men,   text="MEN")
        nb_kadry.add(tab_women, text="WOMEN")
        nb_kadry.add(tab_lato,  text="LATO")
        nb_kadry.add(tab_jun_m, text="JUN-M")
        nb_kadry.add(tab_jun_w, text="JUN-W")

        # Kwoty
        nb_kwoty.add(tab_kwoty,      text="Kwoty")
        nb_kwoty.add(tab_kwoty_lato, text="Kwoty-LATO")
        nb_kwoty.add(tab_rights,     text="Prawa Startów")

        # Wybór
        nb_wybor.add(tab_wybor_m,    text="MEN")
        nb_wybor.add(tab_wybor_w,    text="WOMEN")
        nb_wybor.add(tab_wybor_lato, text="LATO")
        nb_wybor.add(tab_wybor_jun,  text="JUN")
        nb_wybor.add(tab_wybor_ch,   text="CH")
        nb_wybor.add(tab_wybor_jwc,  text="JWC")
        nb_wybor.add(tab_wybor_uni,  text="UNI")
        nb_wybor.add(tab_wybor_yog,  text="YOG")
        nb_wybor.add(tab_wybor_coch, text="COCH")

        self._build_filter_tab(tab_select)
        self._build_wybor_jwc_tab(tab_wybor_jwc)
        self._build_wybor_uni_tab(tab_wybor_uni)
        self._build_wybor_yog_tab(tab_wybor_yog)
        self._build_wybor_lato_tab(tab_wybor_lato)

        # rejestry jak dla innych wyborów (osobno, by się nie mieszało)
        self._wyborJWC_countries = getattr(self, "_wyborJWC_countries", {})
        self._wyborJWC_players   = getattr(self, "_wyborJWC_players", {})
        if not isinstance(self._wyborJWC_countries, dict): self._wyborJWC_countries = {}
        if not isinstance(self._wyborJWC_players, dict):   self._wyborJWC_players   = {}

        # rejestry jak dla JWC, ale osobne dla UNI
        self._wyborUNI_countries = getattr(self, "_wyborUNI_countries", {})
        self._wyborUNI_players   = getattr(self, "_wyborUNI_players", {})
        if not isinstance(self._wyborUNI_countries, dict): self._wyborUNI_countries = {}
        if not isinstance(self._wyborUNI_players, dict):   self._wyborUNI_players   = {}

       # --- Wybór-CH w Kwoty Startowe ---------------------------------------------
        # osobne rejestry widgetów (żeby nie mieszać ze zwykłym Wybór)
        self._wyborCH_countries = getattr(self, "_wyborCH_countries", {})
        self._wyborCH_players   = getattr(self, "_wyborCH_players", {})
        if not isinstance(self._wyborCH_countries, dict): self._wyborCH_countries = {}
        if not isinstance(self._wyborCH_players, dict):   self._wyborCH_players   = {}

        grid_lato = ttk.Frame(tab_lato)
        grid_lato.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        for c in range(4):
            grid_lato.columnconfigure(c, weight=1, uniform="lato4")
            grid_lato.rowconfigure(0, weight=1)

        _build_one_at(grid_lato, 0, 0, "GP-M",   _df_gp_summer())
        _build_one_at(grid_lato, 0, 1, "SCOC-M", _df_scoc_summer())
        _build_one_at(grid_lato, 0, 2, "GP-W",   _df_gp_summer())
        _build_one_at(grid_lato, 0, 3, "SCOC-W", _df_scoc_summer())

        # --- Agregaty: dwie tabele (MEN, WOMEN) z sumą GP+SCOC ---
        agg = ttk.Frame(tab_kwoty_lato)
        agg.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        for c in range(2):
            agg.columnconfigure(c, weight=1, uniform="agg2")
        agg.rowconfigure(0, weight=1)

        # MEN
        box_am = Labeled(agg, "AGREGAT — MEN (GP + SCOC)")
        box_am.grid(row=0, column=0, sticky="nsew", padx=(0,6), pady=6)
        self._kwl_agg_m = Table(box_am.body)
        try:
            self._kwl_agg_m.enable_flags(getattr(self.tab_klasyfikacje, "flag_dir", "./flags"), flag_col="Kraj")
        except Exception:
            pass
        self._kwl_agg_m.pack(fill=tk.BOTH, expand=True)

        # WOMEN
        box_aw = Labeled(agg, "AGREGAT — WOMEN (GP + SCOC)")
        box_aw.grid(row=0, column=1, sticky="nsew", padx=(6,0), pady=6)
        self._kwl_agg_w = Table(box_aw.body)
        try:
            self._kwl_agg_w.enable_flags(getattr(self.tab_klasyfikacje, "flag_dir", "./flags"), flag_col="Kraj")
        except Exception:
            pass
        self._kwl_agg_w.pack(fill=tk.BOTH, expand=True)


        # wewnętrzny notebook: MEN/WOMEN dla CH
        ch_nb = ttk.Notebook(tab_wybor_ch)
        ch_nb.pack(fill=tk.BOTH, expand=True)

        ch_m = ttk.Frame(ch_nb); ch_nb.add(ch_m, text="OG-MEN")
        ch_w = ttk.Frame(ch_nb); ch_nb.add(ch_w, text="OG-WOMEN")

        def _build_one_wybor_ch(container, sex_label: str):
            wrap = ttk.Frame(container); wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

            # Pasek tytułu + odśwież
            top = ttk.Frame(wrap); top.pack(fill=tk.X, pady=(0,6))
            ttk.Label(top, text=f"Wybór-CH – {'Mężczyźni' if sex_label=='M' else 'Kobiety'} (OG, WCH, SFWC, NKIC, IST)")\
                .pack(side="left")
            ttk.Button(top, text="Odśwież", command=lambda s=sex_label: self._refresh_wybor_ch_tab(s))\
                .pack(side="right")

            # 2 kolumny: LEWO (kraje), PRAWO (zawodnicy)
            pw = ttk.Panedwindow(wrap, orient=tk.HORIZONTAL); pw.pack(fill=tk.BOTH, expand=True)

            # --- LEWO
            left = Labeled(pw, "Kraj – WC – COC – FC")
            # pasek sum
            sumbar = ttk.Frame(left.body); sumbar.pack(fill=tk.X, pady=(0,2))
            var_wc  = tk.StringVar(value="WC: 0")
            var_coc = tk.StringVar(value="COC: 0")
            var_fc  = tk.StringVar(value="FC: 0")
            for v in (var_wc, var_coc, var_fc):
                ttk.Label(sumbar, textvariable=v, font=("TkDefaultFont", 9, "bold"))\
                    .pack(side="left", padx=(0, 12))

            tbl_countries = Table(left.body)
            try:
                tbl_countries.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
                if hasattr(tbl_countries, "enable_sorting"):
                    tbl_countries.enable_sorting(numeric_cols=("WC","COC","FC"))
            except Exception:
                pass

            def _on_left_commit_ch(sex=sex_label, t=tbl_countries):
                try:
                    dfc = t.get_dataframe()
                except Exception:
                    dfc = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
                # Prawa: przebuduj prawą tabelę wg zmienionych kwot
                try:
                    dfp = self._players_from_quotas(sex, quotas_df=dfc)
                except Exception:
                    dfp = pd.DataFrame(columns=["Zawodnik","Kraj","Zawody","UM","Forma"])
                for tp in self._wyborCH_players.get(sex, []):
                    try: tp.set_dataframe(dfp)
                    except Exception: pass
                # sumy
                try:
                    total_wc = int(pd.to_numeric(dfc.get("WC",0), errors="coerce").fillna(0).sum())
                    total_coc= int(pd.to_numeric(dfc.get("COC",0), errors="coerce").fillna(0).sum())
                    total_fc = int(pd.to_numeric(dfc.get("FC",0), errors="coerce").fillna(0).sum())
                    var_wc.set(f"WC: {total_wc}"); var_coc.set(f"COC: {total_coc}"); var_fc.set(f"FC: {total_fc}")
                except Exception:
                    pass

            tbl_countries.enable_editing(editable_cols=("WC","COC","FC"),
                                        on_commit=_on_left_commit_ch,
                                        integer_only=True)
            tbl_countries.pack(fill=tk.BOTH, expand=True)
            pw.add(left, weight=1)

            # --- PRAWO: zawodnicy
            right = Labeled(pw, "Zawodnicy (wg kwot CH)")
            tools = ttk.Frame(right.body); tools.pack(fill=tk.X, pady=(0,4))

            tbl_players = FrozenFirstColTable(right.body, frozen_col="Lp.")
            try:
                tbl_players.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
                tbl_players.enable_sorting(numeric_cols=("UM","Forma"))
            except Exception:
                pass
            tbl_players.pack(fill=tk.BOTH, expand=True)
            pw.add(right, weight=2)

            # szybkie zaznaczanie
            def _comp_base_tag(s: str) -> str:
                return re.sub(r"-(?:M|W)$", "", str(s or "").upper().strip())

            def _select_comp(comp: str):
                df = getattr(tbl_players, "_last_df", None)
                if df is None or df.empty or "Zawody" not in df.columns:
                    return
                want = _comp_base_tag(comp)
                tv = tbl_players.tv_main
                try: tv.selection_remove(tv.selection())
                except Exception: pass
                kids = list(tv.get_children())
                base = df["Zawody"].map(_comp_base_tag)
                idxs = df.index[base.eq(want)].tolist()
                for i in idxs:
                    if i < len(kids):
                        tv.selection_add(kids[i])
                if idxs:
                    tv.see(kids[idxs[0]])
                try: tbl_players._sync_from_main(None)
                except Exception: pass

            ttk.Button(tools, text="Zaznacz WC",  command=lambda: _select_comp("WC")).pack(side=tk.LEFT, padx=(0,6))
            ttk.Button(tools, text="Zaznacz COC", command=lambda: _select_comp("COC")).pack(side=tk.LEFT, padx=(0,6))
            ttk.Button(tools, text="Zaznacz FC",  command=lambda: _select_comp("FC")).pack(side=tk.LEFT, padx=(0,6))
            
            ttk.Button(tools, text="Przenieś zaznaczonych do Listy Startowej",
                command=lambda: self._add_players_to_startlist(
                    self._tree_selection_to_df(tbl_players.tv_main,
                        name_col=getattr(tbl_players, "_name_col", "Zawodnik"))
                )).pack(side=tk.RIGHT)

            # rejestr
            self._wyborCH_countries.setdefault(sex_label, []).append(tbl_countries)
            self._wyborCH_players.setdefault(sex_label, []).append(tbl_players)

            # pierwsze wypełnienie
            try:
                dfc = self._compute_wybor_ch_quota(sex_label)
            except Exception:
                dfc = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
            tbl_countries.set_dataframe(dfc)

            try:
                dfp = self._players_from_quotas(sex_label, quotas_df=dfc)
            except Exception:
                dfp = pd.DataFrame(columns=["Zawodnik","Kraj","Zawody","UM","Forma"])
            if "Lp." not in dfp.columns:
                dfp = dfp.copy(); dfp.insert(0, "Lp.", range(1, len(dfp)+1))
            tbl_players.set_dataframe(dfp)

        # zbuduj obie podkarty CH
        _build_one_wybor_ch(ch_m, "M")
        _build_one_wybor_ch(ch_w, "W")
        # --- koniec Wybór-CH w Kwoty Startowe --------------------------------------

        # --- COCH ---
        coch_nb = ttk.Notebook(tab_wybor_coch)
        coch_nb.pack(fill=tk.BOTH, expand=True)

        coch_m = ttk.Frame(coch_nb); coch_nb.add(coch_m, text="COCH-MEN")
        coch_w = ttk.Frame(coch_nb); coch_nb.add(coch_w, text="COCH-WOMEN")

        def _build_one_wybor_coch(container, sex_label: str):
            wrap = ttk.Frame(container); wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            top = ttk.Frame(wrap); top.pack(fill=tk.X, pady=(0,6))
            ttk.Label(top, text=f"Continental Championships – {'M' if sex_label=='M' else 'W'}").pack(side="left")
            ttk.Button(top, text="Odśwież", command=lambda: self._refresh_wybor_coch_tab(sex_label)).pack(side="right")

            pw = ttk.Panedwindow(wrap, orient=tk.HORIZONTAL); pw.pack(fill=tk.BOTH, expand=True)
            
            # LEWO
            left = Labeled(pw, "Kraje (Limit 4)")
            tbl_c = Table(left.body)
            tbl_c.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
            tbl_c.pack(fill=tk.BOTH, expand=True)
            pw.add(left, weight=1)

            # PRAWO
            right = Labeled(pw, "Zawodnicy")
            tools = ttk.Frame(right.body); tools.pack(fill=tk.X, pady=(0,4))
            
            tbl_p = FrozenFirstColTable(right.body, frozen_col="Lp.")
            tbl_p.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
            tbl_p.pack(fill=tk.BOTH, expand=True)
            pw.add(right, weight=2)

            # Przyciski ze skrótami
            buttons_cfg = [
                ("EU", "Europe"), ("AS", "Asia"), ("NA", "North America"),
                ("SA", "South America"), ("AF", "Africa"), ("OC", "Oceania")
            ]
            for short, full in buttons_cfg:
                btn = ttk.Button(tools, text=short, width=4, 
                                 command=lambda f=full: _select_coch_cont(tbl_p, f))
                btn.pack(side="left", padx=2)

            ttk.Button(tools, text="Przenieś do Startlisty", 
                       command=lambda: self._add_players_to_startlist(
                           self._tree_selection_to_df(tbl_p.tv_main))).pack(side="right")

            def _select_coch_cont(tbl, continent_full):
                tv = tbl.tv_main
                tv.selection_set(())
                for iid in tv.get_children():
                    # Teraz sprawdzamy czy wartość w "Zawody" to np. "Europe"
                    if str(tv.set(iid, "Zawody")) == continent_full:
                        tv.selection_add(iid)

            self._wyborCOCH_countries[sex_label] = tbl_c
            self._wyborCOCH_players[sex_label] = tbl_p

        _build_one_wybor_coch(coch_m, "M")
        _build_one_wybor_coch(coch_w, "W")
        # --- KONIEC COCH ---

        # ==== Zakładka: Prawa Startów (MEN/WOMEN) ====
        rights_wrap = ttk.Frame(tab_rights); rights_wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        top_rs = ttk.Frame(rights_wrap); top_rs.pack(fill=tk.X, pady=(0,6))
        ttk.Label(top_rs, text="Prawa Startów – liczba zawodników z prawem startu (WC/COC/FC)").pack(side="left")
        ttk.Button(top_rs, text="Odśwież", command=lambda: self._refresh_rights_tab()).pack(side="right")
        # --- Progi ability: minimalne (0.65*UM + 0.35*Forma) dla MEN/WOMEN i WC/COC/FC ---
        thr_box = Labeled(rights_wrap, "Progi ability – minimalne (0.65·UM + 0.35·Forma)")
        thr_box.pack(fill=tk.X, pady=(0,6))
        thr = thr_box.body

        # defaulty (możesz zmienić na starcie)
        self.var_thr_m_wc = getattr(self, "var_thr_m_wc", tk.DoubleVar(value=90.0))
        self.var_thr_m_coc = getattr(self, "var_thr_m_coc", tk.DoubleVar(value=77.0))
        self.var_thr_m_fc = getattr(self, "var_thr_m_fc", tk.DoubleVar(value=0.0))

        self.var_thr_w_wc = getattr(self, "var_thr_w_wc", tk.DoubleVar(value=75.0))
        self.var_thr_w_coc = getattr(self, "var_thr_w_coc", tk.DoubleVar(value=60.0))
        self.var_thr_w_fc = getattr(self, "var_thr_w_fc", tk.DoubleVar(value=0.0))

        # helper do zbudowania kart JUN-M/W
        def _build_wybor_jun_tab(parent):
            wrap = ttk.Frame(parent); wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

            # pasek narzędzi (odświeżanie z aktualnych list krajów w JUN-M / JUN-W)
            tools = ttk.Frame(wrap); tools.pack(fill=tk.X, pady=(0,6))
            ttk.Label(tools, text=" ").pack(side="left")
            ttk.Button(tools, text="Odśwież", command=lambda: _rebuild_wybor_jun()).pack(side="right")

            # --- [NOWE] wybieraki do zaznaczania po zawodach JUN-M / JUN-W ---
            self.var_jun_m_select = tk.StringVar(value="")
            self.var_jun_w_select = tk.StringVar(value="")

            def _select_in_table_by_comp(tbl, comp_code: str):
                """Zaznacz wiersze w tabeli `tbl`, gdzie kolumna 'Zawody' == comp_code."""
                try:
                    tv = getattr(tbl, "tv_main", getattr(tbl, "tree", None))
                    if tv is None:
                        return
                    # wyczyść zaznaczenie
                    try:
                        tv.selection_set(())
                    except Exception:
                        pass

                    # jeżeli mamy nazwane kolumny, najprościej po .set(iid, "Zawody")
                    selected = []
                    for iid in tv.get_children(""):
                        try:
                            val = tv.set(iid, "Zawody")  # działa jeśli kolumna nazwana „Zawody”
                        except Exception:
                            # fallback: po indeksie kolumny
                            cols = list(tv["columns"])
                            idx = cols.index("Zawody") if "Zawody" in cols else None
                            vals = tv.item(iid).get("values", [])
                            val = vals[idx] if idx is not None and idx < len(vals) else None
                        if str(val).strip().upper() == str(comp_code).strip().upper():
                            selected.append(iid)

                    if selected:
                        try:
                            tv.selection_set(selected)
                            tv.focus(selected[0])
                            tv.see(selected[0])
                        except Exception:
                            pass
                except Exception:
                    pass

            # etykiety + comboboxy
            ttk.Label(tools, text="Zaznacz (JUN-M):").pack(side="left", padx=(12,4))
            cb_jun_m = ttk.Combobox(
                tools,
                textvariable=self.var_jun_m_select,
                values=["JC-M","MC-M","PC-M","QC-M","TC-M","AC-M","BC-M","DC-M"],
                state="readonly", width=8
            )
            cb_jun_m.pack(side="left", padx=(0,8))
            cb_jun_m.bind("<<ComboboxSelected>>",
                        lambda e: _select_in_table_by_comp(getattr(self, "_wybor_jun_tbl_m", None),
                                                            self.var_jun_m_select.get()))

            ttk.Label(tools, text="Zaznacz (JUN-W):").pack(side="left", padx=(12,4))
            cb_jun_w = ttk.Combobox(
                tools,
                textvariable=self.var_jun_w_select,
                values=["JC-W","MC-W","PC-W","QC-W","TC-W","AC-W","BC-W","DC-W"],
                state="readonly", width=8
            )
            cb_jun_w.pack(side="left", padx=(0,8))
            cb_jun_w.bind("<<ComboboxSelected>>",
                        lambda e: _select_in_table_by_comp(getattr(self, "_wybor_jun_tbl_w", None),
                                                            self.var_jun_w_select.get()))
            # --- [KONIEC NOWEGO] ---
            # --- [NOWE] dodawanie zaznaczonych do Listy Startowej z Wybór-JUN ---

            def _jun_push_selected_to_startlist(tbl):
                """
                Zbierz zaznaczonych z podanej tabeli (tbl) i dodaj ich do Listy Startowej,
                używając tej samej ścieżki co w Wybór-MEN/WOMEN.
                """
                tv = getattr(tbl, "tv_main", getattr(tbl, "tree", None))
                if tv is None:
                    return

                # 1) Pobierz DataFrame z aktualnego zaznaczenia
                df_sel = self._tree_selection_to_df(
                    tv,
                    name_col=getattr(tbl, "_name_col", "Zawodnik")
                )
                if df_sel is None or df_sel.empty:
                    return

                # 2) Ujednolicenie najważniejszych kolumn (jeśli istnieją)
                #    (w MEN/WOMEN zwykle przekazujemy Zawodnik/Kraj/UM/Forma/Zawody)
                wanted = [c for c in ["Zawodnik", "Kraj", "UM", "Forma", "Zawody"] if c in df_sel.columns]
                if wanted:
                    df_pass = df_sel[wanted].copy()
                else:
                    df_pass = df_sel.copy()

                # 3) Wywołaj tę samą funkcję, której używasz w MEN/WOMEN
                #    (próba kilku popularnych nazw — wybierz tę, którą masz u siebie)
                self._add_players_to_startlist(df_pass)

                # 4) Awaryjnie: jeśli nie trafiło w nazwę, spróbuj istniejącego handlera z MEN/WOMEN,
                #    jeśli masz go pod ręką jako callback:
                handler = getattr(self, "_wybor_add_selected_handler", None)
                if callable(handler):
                    try:
                        handler(df_pass)
                        return
                    except Exception:
                        pass
                # Jeśli tu dotarliśmy, to znaczy, że w Twoim kodzie funkcja nazywa się inaczej.
                # Podmień w pętli wyżej nazwę na tę, której używasz w MEN/WOMEN.
                # --- koniec awaryjnego fallbacku ---

            # Przyciski obok comboboxów:
            ttk.Button(tools, text="JUN-W → Listy",
                command=lambda: _jun_push_selected_to_startlist(getattr(self, "_wybor_jun_tbl_w", None))
            ).pack(side="right", padx=(8,0))

            ttk.Button(tools, text="JUN-M → Listy",
                command=lambda: _jun_push_selected_to_startlist(getattr(self, "_wybor_jun_tbl_m", None))
            ).pack(side="right", padx=(8,0))

            # (Opcjonalnie) Jeden zbiorczy przycisk dla obu tabel:
            # ttk.Button(
            #     tools,
            #     text="Dodaj zazn. (obie tabele)",
            #     command=lambda: [
            #         _jun_push_selected_to_startlist(getattr(self, "_wybor_jun_tbl_m", None)),
            #         _jun_push_selected_to_startlist(getattr(self, "_wybor_jun_tbl_w", None)),
            #     ]
            # ).pack(side="left", padx=(0, 6))
            # --- [KONIEC NOWEGO] ---


            # dwie kolumny obok siebie
            cols = ttk.Panedwindow(wrap, orient="horizontal")
            cols.pack(fill=tk.BOTH, expand=True)

            left_frame  = ttk.Frame(cols)
            right_frame = ttk.Frame(cols)
            cols.add(left_frame,  weight=1)   # oba panele elastyczne
            cols.add(right_frame, weight=1)

            left  = Labeled(left_frame,  "JUN-M")
            right = Labeled(right_frame, "JUN-W")
            left.pack(fill=tk.BOTH, expand=True, padx=(0,4))
            right.pack(fill=tk.BOTH, expand=True, padx=(4,0))

            tbl_m = FrozenFirstColTable(left.body,  frozen_col="Lp.")
            tbl_w = FrozenFirstColTable(right.body, frozen_col="Lp.")
            tbl_m.pack(fill=tk.BOTH, expand=True)
            tbl_w.pack(fill=tk.BOTH, expand=True)

            # flaga przy nazwisku
            try:
                flag_dir = getattr(self.tab_klasyfikacje, "flag_dir", "./flags")
            except Exception:
                flag_dir = "./flags"
            tbl_m.enable_flags_after_name(flag_dir, kraj_col="Kraj", name_col="Zawodnik")
            tbl_w.enable_flags_after_name(flag_dir, kraj_col="Kraj", name_col="Zawodnik")

            tbl_m.enable_sorting(numeric_cols=("Wiek", "UM", "Forma"))
            tbl_w.enable_sorting(numeric_cols=("Wiek", "UM", "Forma"))

            # zapamiętaj referencje
            self._wybor_jun_tbl_m = tbl_m
            self._wybor_jun_tbl_w = tbl_w

            # pierwsze wypełnienie
            _rebuild_wybor_jun()

        # generator danych do Wybór-JUN
        def _rebuild_wybor_jun():
            

            tbl_m = getattr(self, "_wybor_jun_tbl_m", None)
            tbl_w = getattr(self, "_wybor_jun_tbl_w", None)
            if tbl_m is None or tbl_w is None:
                return

            try:
                dfm = self._players_from_jun_countries("M", per_country=3)
            except Exception:
                dfm = pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])
            try:
                dfw = self._players_from_jun_countries("W", per_country=3)
            except Exception:
                dfw = pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

            cols = ["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"]
            dfm = dfm.reindex(columns=cols, fill_value=pd.NA)
            dfw = dfw.reindex(columns=cols, fill_value=pd.NA)

            tbl_m.set_dataframe(dfm)
            tbl_w.set_dataframe(dfw)

            # kosmetyka szerokości
            for t in (tbl_m, tbl_w):
                try:
                    t.tv_fixed.column("Lp.", width=52, anchor="e", stretch=False)
                    tv = t.tv_main
                    tv.column("Zawodnik", width=240, anchor="w")
                    tv.column("Kraj",      width=90,  anchor="w")
                    tv.column("Wiek",      width=60,  anchor="e")
                    tv.column("Zawody",    width=70,  anchor="center")
                    tv.column("UM",        width=60,  anchor="e")
                    tv.column("Forma",     width=60,  anchor="e")
                except Exception:
                    pass

        # zbuduj faktyczną kartę „Wybór-JUN”
        _build_wybor_jun_tab(tab_wybor_jun)

        # helper do tworzenia rzędu z 3 spinboxami + opcjonalny przycisk "Przelicz"
        def _make_thr_row(parent, title, v_wc, v_coc, v_fc, add_apply=False, apply_after_wc=False):
            row = ttk.Frame(parent); row.pack(side="left", padx=(0,24))
            ttk.Label(row, text=title, font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0,8))

            ttk.Label(row, text="WC").grid(row=0, column=1, sticky="w")
            sb_wc = ttk.Spinbox(row, from_=0.0, to=200.0, increment=0.5, width=6, textvariable=v_wc)
            sb_wc.grid(row=0, column=2, sticky="w", padx=(2,10))

            col = 3
            if add_apply and apply_after_wc:
                ttk.Button(row, text="Przelicz", command=lambda: self._refresh_rights_tab())\
                .grid(row=0, column=col, sticky="w", padx=(8,10))
                col += 1  # przesuwamy dalsze pola w prawo

            ttk.Label(row, text="COC").grid(row=0, column=col, sticky="w"); col += 1
            sb_coc = ttk.Spinbox(row, from_=0.0, to=200.0, increment=0.5, width=6, textvariable=v_coc)
            sb_coc.grid(row=0, column=col, sticky="w", padx=(2,10)); col += 1

            ttk.Label(row, text="FC").grid(row=0, column=col, sticky="w"); col += 1
            sb_fc = ttk.Spinbox(row, from_=0.0, to=200.0, increment=0.5, width=6, textvariable=v_fc)
            sb_fc.grid(row=0, column=col, sticky="w", padx=(2,0))

            if add_apply and not apply_after_wc:
                ttk.Button(row, text="Przelicz", command=lambda: self._refresh_rights_tab())\
                .grid(row=0, column=col+1, sticky="w", padx=(12,0))

        # dwa bloki: MEN i WOMEN
        _make_thr_row(thr, "MEN",   self.var_thr_m_wc, self.var_thr_m_coc, self.var_thr_m_fc, add_apply=False)
        _make_thr_row(thr, "WOMEN", self.var_thr_w_wc, self.var_thr_w_coc, self.var_thr_w_fc, add_apply=True)

        pw_rs = ttk.Panedwindow(rights_wrap, orient=tk.HORIZONTAL); pw_rs.pack(fill=tk.BOTH, expand=True)

        # MEN table
        box_m = Labeled(pw_rs, "MEN")
        tbl_rs_m = Table(box_m.body)
        try:
            tbl_rs_m.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
        except Exception:
            pass
        try:
            tbl_rs_m.enable_sorting(numeric_cols=("WC","COC","FC"))
        except Exception:
            pass
        tbl_rs_m.pack(fill=tk.BOTH, expand=True)
        pw_rs.add(box_m, weight=1)

        # WOMEN table
        box_w = Labeled(pw_rs, "WOMEN")
        tbl_rs_w = Table(box_w.body)
        try:
            tbl_rs_w.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
        except Exception:
            pass
        try:
            tbl_rs_w.enable_sorting(numeric_cols=("WC","COC","FC"))
        except Exception:
            pass
        tbl_rs_w.pack(fill=tk.BOTH, expand=True)
        pw_rs.add(box_w, weight=1)

        # Referencje do tabel
        self._rights_tables = {"M": tbl_rs_m, "W": tbl_rs_w}

        def _compute_rights_df(sex: str):
            
            

            df_full = getattr(self, "_roster_df_cache", None)
            if df_full is None or df_full.empty:
                try:
                    nats = sorted(set(self._all_known_countries()))
                except Exception:
                    nats = []
                return pd.DataFrame({"Kraj": nats, "WC": 0, "COC": 0, "FC": 0})

            pool = df_full.copy()
            for c in ("Zawodnik","Kraj","Płeć","PrawoStartu","UM","Forma"):
                if c not in pool.columns:
                    pool[c] = 0 if c in ("PrawoStartu","UM","Forma") else ""
            if "Płeć" in pool.columns:
                pool = pool[pool["Płeć"].astype(str).str.upper().eq(sex)]

            # ability = 0.65*UM + 0.35*Forma (wagi stałe)
            um = pd.to_numeric(pool.get("UM", 50), errors="coerce").fillna(50.0)
            fo = pd.to_numeric(pool.get("Forma", 50), errors="coerce").fillna(50.0)
            pool["__ability"] = 0.65*um + 0.35*fo
            pool["__PS"] = pd.to_numeric(pool.get("PrawoStartu", 0), errors="coerce").fillna(0).astype(int)

            # limity PS (niezmienne)
            ps_max = {"WC": 3, "COC": 6, "FC": 7}

            # progi z GUI (MEN/WOMEN)
            if sex == "M":
                thr = {
                    "WC": float(self.var_thr_m_wc.get() or 0),
                    "COC": float(self.var_thr_m_coc.get() or 0),
                    "FC": float(self.var_thr_m_fc.get() or 0),
                }
            else:
                thr = {
                    "WC": float(self.var_thr_w_wc.get() or 0),
                    "COC": float(self.var_thr_w_coc.get() or 0),
                    "FC": float(self.var_thr_w_fc.get() or 0),
                }

            counts = {}
            for comp in ("WC","COC","FC"):
                # bazowy filtr PS/wiek/itd. z istniejącej logiki
                try:
                    base = self._filter_df_for_comp_sex(pool, comp, sex).copy()
                except Exception:
                    base = pool.copy()
                if base.empty:
                    counts[comp] = {}
                    continue

                # PS <= {3,6,7}
                base = base[pd.to_numeric(base["__PS"], errors="coerce").fillna(1e9) <= ps_max[comp]]
                # ability >= próg z GUI
                base = base[pd.to_numeric(base["__ability"], errors="coerce").fillna(-1e9) >= thr[comp]]

                grp = base.groupby(base["Kraj"].astype(str).str.upper()).size()
                counts[comp] = grp.to_dict()

            try:
                all_nats = set().union(*[set(d.keys()) for d in counts.values()])
                all_nats |= set(self._all_known_countries())
            except Exception:
                all_nats = set().union(*[set(d.keys()) for d in counts.values()])

            rows = []
            for nat in sorted(all_nats):
                rows.append({
                    "Kraj": nat,
                    "WC": int(counts.get("WC", {}).get(nat, 0)),
                    "COC": int(counts.get("COC", {}).get(nat, 0)),
                    "FC": int(counts.get("FC", {}).get(nat, 0)),
                })
            return pd.DataFrame(rows)

        # Odświeżanie zakładki
        def _refresh_rights():
            try:
                for sex in ("M","W"):
                    df_rs = _compute_rights_df(sex)
                    self._last_rights_df = getattr(self, "_last_rights_df", {})
                    self._last_rights_df[sex] = df_rs[["Kraj","WC","COC","FC"]].copy()
                    tbl = self._rights_tables.get(sex)
                    if tbl:
                        tbl.set_dataframe(df_rs)
            except Exception as e:
                print("[Prawa Startów] refresh error:", e)

        # publiczny hook
        self._refresh_rights_tab = _refresh_rights
        # inicjalne wypełnienie
        self._refresh_rights_tab()

        # --- osobne „rejestry” widżetów dla KWOT (nie mieszaj z WYBÓR) ---
        self._kwoty_countries = getattr(self, "_kwoty_countries", {})
        self._kwoty_players   = getattr(self, "_kwoty_players", {})

        def _build_one_kwoty(container, sex_label: str):
            """Zakładka: Kwoty – stałe (tylko MEN/WOMEN). Bez prawej tabeli."""
            wrap = ttk.Frame(container); wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

            # Nagłówek
            top = ttk.Frame(wrap); top.pack(fill=tk.X, pady=(0,6))
            ttk.Label(top, text=f"Kwoty – {'Mężczyźni' if sex_label=='M' else 'Kobiety'}").pack(side="left")

            # LEWA strona: tylko kraje z kwotami
            left = Labeled(wrap, "Kraj – WC – COC – FC")
            left.pack(fill=tk.BOTH, expand=True)

            tbl_countries = Table(left.body)
            try:
                tbl_countries.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
                # sortowanie po liczbach (gdy klikniesz nagłówek)
                if hasattr(tbl_countries, "enable_sorting"):
                    tbl_countries.enable_sorting(numeric_cols=("WC", "COC", "FC"))
            except Exception:
                pass
            tbl_countries.pack(fill=tk.BOTH, expand=True)

            # rejestruj tylko lewą tabelę
            self._kwoty_countries.setdefault(sex_label, []).append(tbl_countries)

            # pierwszy render
            self._refresh_kwoty_tab(sex_label)

        def _build_one_wybor(container, sex_label: str, title_prefix="Wybór"):
            wrap = ttk.Frame(container); wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

            # Pasek tytułu + odśwież
            top = ttk.Frame(wrap); top.pack(fill=tk.X, pady=(0,6))
            ttk.Label(top, text=f"{title_prefix} – {'Mężczyźni' if sex_label=='M' else 'Kobiety'}").pack(side="left")
            ttk.Button(top, text="Odśwież z kwot",
                      command=lambda s=sex_label: self._on_refresh_from_quotas(s)).pack(side="right")

            # 2 kolumny: LEWO (kraje), PRAWO (zawodnicy)
            pw = ttk.Panedwindow(wrap, orient=tk.HORIZONTAL); pw.pack(fill=tk.BOTH, expand=True)

            # --- LEWO: kraje
            left = Labeled(pw, "Kraj – WC – COC – FC")

            # [NOWE] Pasek sum nad kolumnami
            self._wybor_sumvars = getattr(self, "_wybor_sumvars", {})
            sumbar = ttk.Frame(left.body); sumbar.pack(fill=tk.X, pady=(0, 2))
            var_wc  = tk.StringVar(value="WC: 0")
            var_coc = tk.StringVar(value="COC: 0")
            var_fc  = tk.StringVar(value="FC: 0")
            for v in (var_wc, var_coc, var_fc):
                ttk.Label(sumbar, textvariable=v, font=("TkDefaultFont", 9, "bold"))\
                .pack(side="left", padx=(0, 12))
            # zapamiętaj zestaw zmiennych dla danej płci (M/W)
            self._wybor_sumvars[sex_label] = (var_wc, var_coc, var_fc)
            
            tbl_countries = Table(left.body)
            
            # ✔ WŁĄCZ EDYCJĘ: WC/COC/FC edytowalne; po zapisie odśwież prawą tabelę
            def _on_left_commit(sex=sex_label, t=tbl_countries):
                try:
                    dfc = t.get_dataframe()
                    self._update_wybor_sums(sex, dfc)
                except Exception:
                    
                    dfc = pd.DataFrame(columns=["Kraj","WC","COC","FC"])
                # przelicz prawą tabelę z nowych kwot
                try:
                    dfp = self._players_from_quotas(sex, quotas_df=dfc)
                except Exception:
                    
                    dfp = pd.DataFrame(columns=["Zawodnik","Kraj","Zawody","UM","Forma"])
                for tp in self._wybor_players.get(sex, []):
                    try:
                        tp.set_dataframe(dfp)
                    except Exception:
                        pass

            tbl_countries.enable_editing(editable_cols=("WC","COC","FC"),
                                         on_commit=_on_left_commit,
                                         integer_only=True)

            try: tbl_countries.enable_flags_after_name(FLAGS_DIR, "Kraj", "Kraj")
            except Exception: pass
            
            try:
                tbl_countries.enable_sorting(numeric_cols=("WC", "COC", "FC"))
            except Exception:
                pass
            
            tbl_countries.pack(fill=tk.BOTH, expand=True)
            pw.add(left, weight=1)

            # --- PRAWO: zawodnicy + toolbar z przyciskami
            right = Labeled(pw, "Zawodnicy (wg kwot)")

            tools = ttk.Frame(right.body); tools.pack(fill=tk.X, pady=(0,4))

            tbl_players = FrozenFirstColTable(right.body, frozen_col="Lp.")
            try:
                tbl_players.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
                tbl_players.enable_sorting(numeric_cols=("UM","Forma"))
            except Exception:
                pass
            tbl_players.pack(fill=tk.BOTH, expand=True)
            pw.add(right, weight=2)

            # === logika przycisków ===
            def _select_comp(comp: str):
                df = getattr(tbl_players, "_last_df", None)
                if df is None or df.empty or "Zawody" not in df.columns:
                    return
                want = _comp_base_tag(comp)
                tv = tbl_players.tv_main
                try:
                    tv.selection_remove(tv.selection())
                except Exception:
                    pass

                # Jeśli TEAM zaznaczony — wyklucz kraje z miejsc 9-11 rankingu WC
                excluded_nats = set()
                if team_var.get():
                    QUOTA_PLACES = {9, 10, 11}
                    wc_tag = f"WC-{sex_label}"
                    try:
                        wc_df = self.tab_klasyfikacje.get_nation_ranking(wc_tag)
                        if wc_df is not None and not wc_df.empty:
                            wc_df = wc_df.reset_index(drop=True)
                            wc_df["__miejsce__"] = wc_df.index + 1
                            excluded_nats = set(
                                wc_df.loc[wc_df["__miejsce__"].isin(QUOTA_PLACES), "NAT"]
                                .astype(str).str.upper().tolist()
                            )
                    except Exception:
                        pass

                kids = list(tv.get_children())
                base = df["Zawody"].map(_comp_base_tag)
                # nowe:
                seen_excluded = set()
                idxs = []
                for i in df.index[base.eq(want)].tolist():
                    nat = str(df.loc[i, "Kraj"]).strip().upper()
                    if nat in excluded_nats:
                        if nat not in seen_excluded:
                            seen_excluded.add(nat)  # pierwszy z tego kraju — pomijamy
                        else:
                            idxs.append(i)          # drugi i kolejni — zaznaczamy normalnie
                    else:
                        idxs.append(i)

                for i in idxs:
                    if i < len(kids):
                        tv.selection_add(kids[i])
                if idxs:
                    tv.see(kids[idxs[0]])
                try:
                    tbl_players._sync_from_main(None)
                except Exception:
                    pass

            def _select_quota_nations(comp: str):
                """
                Pobiera kraje z miejsc 9, 10, 11 rankingu WC-M/WC-W,
                następnie zaznacza pierwszego zawodnika z każdego takiego kraju
                który ma w kolumnie 'Zawody' wartość pasującą do `comp` (COC lub FC).
                """
                QUOTA_PLACES = {9, 10, 11}
                wc_tag = f"WC-{sex_label}"   # "WC-M" lub "WC-W"

                # Pobierz ranking WC z KlasyfikacjeTab
                try:
                    wc_df = self.tab_klasyfikacje.get_nation_ranking(wc_tag)
                except Exception:
                    return
                if wc_df is None or wc_df.empty:
                    return

                # Kraje z miejsc 9, 10, 11
                wc_df = wc_df.reset_index(drop=True)
                wc_df["__miejsce__"] = wc_df.index + 1
                quota_nats = set(
                    wc_df.loc[wc_df["__miejsce__"].isin(QUOTA_PLACES), "NAT"]
                    .astype(str).str.upper().tolist()
                )
                if not quota_nats:
                    return

                # Filtruj zawodników po kraju ORAZ po typie zawodów (COC lub FC)
                df = getattr(tbl_players, "_last_df", None)
                if df is None or df.empty or "Kraj" not in df.columns:
                    return

                want = _comp_base_tag(comp)   # "COC" lub "FC"

                tv = tbl_players.tv_main
                try:
                    tv.selection_remove(tv.selection())
                except Exception:
                    pass

                kids = list(tv.get_children())
                already_picked = set()

                for i, row in df.iterrows():
                    nat  = str(row.get("Kraj", "")).strip().upper()
                    zawody = _comp_base_tag(str(row.get("Zawody", "")))
                    if nat in quota_nats and zawody == want and nat not in already_picked:
                        if i < len(kids):
                            tv.selection_add(kids[i])
                            already_picked.add(nat)

                if already_picked:
                    first_sel = tv.selection()
                    if first_sel:
                        tv.see(first_sel[0])
                try:
                    tbl_players._sync_from_main(None)
                except Exception:
                    pass

            def _move_selected_from_players():
                df_sel = self._tree_selection_to_df(tbl_players.tv_main, name_col="Zawodnik")
                if df_sel is None or df_sel.empty:
                    return
                keep = [c for c in ["Zawodnik","Kraj","UM","Forma"] if c in df_sel.columns] or list(df_sel.columns)
                df_sel = df_sel[keep].copy()

                if not hasattr(self, "selected_df") or self.selected_df is None:
                    self.selected_df = pd.DataFrame(columns=keep)
                base = self.selected_df.copy()
                for c in keep:
                    if c not in base.columns:
                        base[c] = ""

                key = [c for c in ("Zawodnik","Kraj") if c in df_sel.columns and c in base.columns] or ["Zawodnik"]
                exist = set(tuple(x) for x in base[key].astype(str).to_records(index=False))
                to_add = df_sel[~df_sel[key].astype(str).apply(tuple, axis=1).isin(exist)]

                self.selected_df = pd.concat([base[keep], to_add[keep]], ignore_index=True)
                self._refresh_startlist_view()

            # Przyciski
            ttk.Button(tools, text="Zaznacz WC",  command=lambda: _select_comp("WC")).pack(side=tk.LEFT, padx=(0,6))
            ttk.Button(tools, text="Zaznacz COC", command=lambda: _select_comp("COC")).pack(side=tk.LEFT, padx=(0,6))
            ttk.Button(tools, text="Zaznacz FC",  command=lambda: _select_comp("FC")).pack(side=tk.LEFT, padx=(0,6))
            team_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(tools, text="TEAM", variable=team_var).pack(side=tk.LEFT, padx=(0,12))

            ttk.Button(tools, text="Przenieś zaznaczonych do Listy Startowej",
                command=lambda: self._add_players_to_startlist(
                    self._tree_selection_to_df(tbl_players.tv_main, name_col=getattr(tbl_players, "_name_col", "Zawodnik"))
                )).pack(side=tk.RIGHT)

            # Rejestry do późniejszego odświeżania
            self._wybor_countries.setdefault(sex_label, []).append(tbl_countries)
            self._wybor_players.setdefault(sex_label, []).append(tbl_players)

            # Pierwsze wypełnienie
            try:
                dfc = self._compute_wybor_min_quota(sex_label)
            except Exception:
                
                dfc = pd.DataFrame(columns=["Kraj","WC","COC","FC"])

            tbl_countries.set_dataframe(dfc)

            # zapamiętaj DF i przelicz sumy po idle (to już masz)
            self._wybor_last_dfc = getattr(self, "_wybor_last_dfc", {})
            self._wybor_last_dfc[sex_label] = dfc.copy() if hasattr(dfc, "copy") else dfc
            try:
                self.after_idle(lambda s=sex_label: self._update_wybor_sums(s, self._wybor_last_dfc[s]))
            except Exception:
                self._update_wybor_sums(sex_label, dfc)

            # >>> DODAJ / PRZENIEŚ TO NIŻEJ <<<
            # zbuduj prawą tabelę zawodników z efektywnych kwot
            try:
                dfp = self._players_from_quotas(sex_label, quotas_df=dfc)
            except Exception:
                
                dfp = pd.DataFrame(columns=["Zawodnik","Kraj","Zawody","UM","Forma"])

            # Wymuś obecność 'Lp.' żeby zamrożona 1. kolumna działała
            if "Lp." not in dfp.columns:
                dfp = dfp.copy()
                dfp.insert(0, "Lp.", range(1, len(dfp)+1))

            tbl_players.set_dataframe(dfp)
            try:
                tbl_players.tv_main.bind("<Double-1>", lambda e: _move_selected_from_players())
            except Exception:
                pass

        _build_one_wybor(tab_wybor_m, "M", title_prefix="Wybór")
        _build_one_wybor(tab_wybor_w, "W", title_prefix="Wybór")

        # Kwoty – stałe (bez przycisku)
        kw_split = ttk.Panedwindow(tab_kwoty, orient=tk.HORIZONTAL)
        kw_split.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        kw_m = ttk.Frame(kw_split); kw_split.add(kw_m, weight=1)
        kw_w = ttk.Frame(kw_split); kw_split.add(kw_w, weight=1)

        # użyj tego samego konstruktora co wcześniej
        _build_one_kwoty(kw_m, "M")
        _build_one_kwoty(kw_w, "W")

        # ——— kontener tabel 3×1 ———
        def _mk_grid(host):
            grid = ttk.Frame(host)
            grid.pack(fill=tk.BOTH, expand=True)
            for c in range(3):
                grid.columnconfigure(c, weight=1)
            grid.rowconfigure(0, weight=1)
            return grid

        # ——— budowa pojedynczej tabeli ———
        if not hasattr(self, "quota_tables"):
            self.quota_tables = {}  # np. {"WC-M": Table, "COC-W": Table, ...}

        def _build_one(grid, col, title, df):
            box = Labeled(grid, title)
            box.grid(row=0, column=col, sticky="nsew", padx=6, pady=6)
            t = Table(box.body)
            t.enable_flags(getattr(self.tab_klasyfikacje, "flag_dir", "./flags"), flag_col="Pozycja")
            t.pack(fill=tk.BOTH, expand=True)
            t.set_dataframe(df[["Pozycja", "Ilość"]].copy())
            # szerokości kolumn
            try:
                tv = t.tree
                tv.column("Pozycja", width=120, minwidth=100, stretch=True)
                tv.column("Ilość", width=70, minwidth=60, stretch=False, anchor="center")
            except Exception:
                pass
            return t

        def _build_three(host, sex_suffix):
            grid = _mk_grid(host)
            mapping = [("WC", _df_wc()), ("COC", _df_coc()), ("FC", _df_fc())]
            for idx, (tag, df) in enumerate(mapping):
                key = f"{tag}-{sex_suffix}"
                self.quota_tables[key] = _build_one(grid, idx, key, df)

        # ——— MEN & WOMEN ———
        _build_three(tab_men, "M")
        _build_three(tab_women, "W")

        # --- JUNIORZY 8×1 (pionowo): JC, MC, PC, QC, TC, AC, BC, DC ---
        jun_tags = ["JC","MC","PC","QC","TC","AC","BC","DC"]

        # siatka 8×1 (jedna kolumna)
        for f in (tab_jun_m, tab_jun_w):
            for i in range(8):
                f.grid_columnconfigure(i, weight=1, uniform="jun")
            f.grid_rowconfigure(0, weight=1)

        # JUN-M
        for idx, comp in enumerate(jun_tags):
            r, c = 0, idx
            _build_one_at_jun_onecol(tab_jun_m, r, c, f"{comp}-M", _df_jun())

        # JUN-W (8×1)
        for idx, comp in enumerate(jun_tags):
            r, c = 0, idx
            _build_one_at_jun_onecol(tab_jun_w, r, c, f"{comp}-W", _df_jun())

        # --- toolbar do uzupełniania wg Klasyfikacji ---
        tools = ttk.Frame(parent); tools.pack(fill=tk.X, padx=8, pady=(0,6))
        info_lbl = ttk.Label(tools, text="", foreground="#666")
        def _rebuild_default_df(comp: str) -> pd.DataFrame:
            if comp.startswith("WC"):
                return _df_wc()
            if comp.startswith("COC"):
                return _df_coc()
            if comp.startswith("FC"):
                return _df_fc()
            if comp.startswith("GP"):
                return _df_gp_summer()
            if comp.startswith("SCOC"):
                return _df_scoc_summer()
            # >>> JUNIORZY:
            if comp in ("JC","MC","PC","QC","TC","AC","BC","DC"):
                return _df_jun()
            return pd.DataFrame({"Pozycja": [], "Ilość": []})

        def _apply_from_classif():
            """
            Wpisuje kody krajów (NAT) wg klasyfikacji do tabel kwot.
            FC-: 'Pozostali z pkt' → lista krajów poza TOP18 z punktami (Ilość=2).
            """
            try:
                base_tags = ["WC","COC","FC", "GP", "SCOC"]
                jun_tags = ["JC","MC","PC","QC","TC","AC","BC","DC"]
                all_comp = base_tags + jun_tags

                mapping = [(comp, sex) for comp in all_comp for sex in ("M","W")]
                filled = 0
                fc_expanded = []

                for comp, sex in mapping:
                    key = f"{comp}-{sex}"
                    try:
                        ranks = self.tab_klasyfikacje.get_nation_ranking(key)
                    except Exception:
                        ranks = pd.DataFrame()

                    base = _rebuild_default_df(comp)
                    if base.empty:
                        continue

                    is_num = base["Pozycja"].apply(lambda x: isinstance(x, (int, np.integer)))
                    idxs   = list(base[is_num].index)
                    topN   = min(len(idxs), len(ranks))

                    def _nat(row):
                        code = str(row.get("NAT", "") or "").strip()
                        if not code:
                            code = str(row.get("NATION", "") or "").strip()
                        return code

                    for i in range(topN):
                        base.at[idxs[i], "Pozycja"] = _nat(ranks.iloc[i])

                    jun_tags = {"JC","MC","PC","QC","TC","AC","BC","DC"}
                    key = f"{comp}-{sex}"
                    t = self.quota_tables.get(key)
                    if t is None:
                        continue

                    # ranks: DataFrame lub Series z kodami krajów (NAT)
                    def _nat(rowlike):
                        try:
                            return str(rowlike.get("NAT", "")).strip().upper()
                        except Exception:
                            return str(rowlike).strip().upper()

                    if comp in jun_tags:
                        # --- JUN: wczytaj z CSV bez limitu makiety ---
                        nat_list = []
                        if hasattr(ranks, "iterrows"):
                            for _, r in ranks.iterrows():
                                code = _nat(r)
                                if code:
                                    nat_list.append(code)
                        else:
                            nat_list = [_nat(x) for x in list(ranks)]

                        # → SORTOWANIE A–Z po kodzie kraju (3-literowym)
                        # (usuwamy puste, podnosimy do UPPER i sortujemy)
                        clean_sorted = sorted(
                            (c.strip().upper() for c in nat_list if c and str(c).strip()),
                            key=str.upper
                        )

                        df_view = pd.DataFrame({"Kraj": clean_sorted})
                        t.set_dataframe(df_view)

                        # kosmetyka nagłówka/kolumny
                        try:
                            tv = t.tree
                            tv.heading("Kraj", text="Kraj")
                            tv.column("Kraj", width=200, minwidth=140, stretch=True, anchor="w")
                        except Exception:
                            pass

                        continue
                    
                    # Specjalna logika tylko dla FC-
                    # --- NOWE: rozbij "Pozostali bez pkt" (po 1 miejscu dla każdego) ---
                    # --- ROZBIJ "Pozostali z pkt" (po 2 miejsca) ---
                    if comp == "FC":
                        # 1) punkty wg klasyfikacji
                        pts_map = {}
                        if isinstance(ranks, pd.DataFrame) and not ranks.empty and "NAT" in ranks.columns:
                            r2 = ranks.copy()
                            r2["PTS"] = pd.to_numeric(r2.get("PTS", 0), errors="coerce").fillna(0.0)
                            pts_map = dict(zip(r2["NAT"].astype(str).str.upper(), r2["PTS"]))

                        # 2) kraje już wpisane w tabeli (TOP pozycje itd.) – żeby nie dublować
                        already = set()
                        for x in base["Pozycja"].astype(str):
                            m = re.search(r"\b[A-Z]{3}\b", x.upper())
                            if m:
                                already.add(m.group(0))

                        # 3) „z pkt” = wszystkie z PTS>0, których jeszcze nie wpisaliśmy
                        with_pts = sorted(n for n, p in pts_map.items() if p > 0 and n not in already)

                        if with_pts:
                            add2 = pd.DataFrame({"Pozycja": with_pts, "Ilość": [2] * len(with_pts)})
                            m = base["Pozycja"].astype(str).str.strip().str.lower().eq("pozostali z pkt")
                            idxs = list(base[m].index)
                            if idxs:
                                i = idxs[0]
                                base = pd.concat([base.iloc[:i], add2, base.iloc[i+1:]], ignore_index=True)
                            else:
                                base = pd.concat([base, add2], ignore_index=True)

                    t = self.quota_tables.get(key)
                    if t is not None:
                        if comp in ("JC","MC","PC","QC","TC","AC","BC","DC"):
                            # JUN: tylko jedna kolumna „Kraj”
                            df_view = base[["Pozycja"]].copy().rename(columns={"Pozycja": "Kraj"})
                            t.set_dataframe(df_view)
                            try:
                                tv = t.tree
                                tv.heading("Kraj", text="Kraj")
                                tv.column("Kraj", width=200, minwidth=140, stretch=True, anchor="w")
                            except Exception:
                                pass
                        else:
                            # WC/COC/FC: Pozycja + Ilość (bez zmian)
                            t.set_dataframe(base[["Pozycja","Ilość"]].copy())
                            try:
                                tv = t.tree
                                tv.column("Pozycja", width=160, minwidth=120, stretch=True)
                                tv.column("Ilość",   width=70,  minwidth=60,  stretch=False, anchor="center")
                            except Exception:
                                pass
                    filled += topN

                # po uzupełnieniu MEN/WOMEN z klasyfikacji – odśwież stałe zakładki Kwoty
                try:
                    self._refresh_kwoty_tab("M")
                    self._refresh_kwoty_tab("W")
                except Exception:
                    pass
                try:
                    # odśwież agregaty LATO (GP+SCOC) dla MEN/WOMEN
                    self._refresh_kwoty_lato_aggregates()
                except Exception:
                    pass
                
                if fc_expanded:
                    msg += f" FC: rozbito 'Pozostali z pkt' dla: {', '.join(fc_expanded)}."
                info_lbl.config(text=msg)
            except Exception as e:
                info_lbl.config(text=f"Nie udało się uzupełnić: {e}")
        # --- NOWE: wczytaj juniorów z S45/Juniorzy S45.csv i wypełnij JC..DC (M/W) ---
        def _fill_junior_quotas_from_file(csv_path: str | None = None):

            try:
                path = Path(csv_path or "S45/Juniorzy S45.csv")
                if not path.exists():
                    messagebox.showerror("Juniorzy – plik",
                                         f"Nie znaleziono pliku: {path}\nUpewnij się, że jest w folderze S45.")
                    return

                # CSV jest oddzielany ';', pierwsze wiersze mogą mieć puste komórki separatora
                df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig")
                # znormalizuj nazwy kolumn, usuń ew. bezimienne/puste
                df.columns = [str(c).strip() for c in df.columns]
                if "" in df.columns:
                    df = df.drop(columns=[c for c in df.columns if str(c).strip() == ""])

                # Usuń wiersze całkiem puste
                df = df.replace({None: "", pd.NA: ""}).fillna("")
                df = df[~(df.applymap(lambda x: str(x).strip() == "").all(axis=1))]

                JUN_TAGS = ("JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC")

                # zrób mapę { 'JC-M': [AUT, ...], 'JC-W': [NOR, ...], ... }
                data_map = {}
                for col in df.columns:
                    name = str(col).strip().upper()
                    # oczekujemy nagłówków typu JC-M ... DC-W
                    if "-" not in name:
                        continue
                    prefix, sex = name.split("-", 1)
                    sex = sex.strip()
                    if prefix in JUN_TAGS and sex in ("M", "W"):
                        vals = [str(v).strip().upper() for v in df[col].tolist() if str(v).strip()]
                        # odfiltruj śmieci i duplikaty, posortuj alfabetycznie
                        vals = sorted({v for v in vals if len(v) >= 3})
                        data_map[f"{prefix}-{sex}"] = vals

                if not data_map:
                    messagebox.showwarning("Juniorzy – plik",
                                           "Nie znaleziono żadnych kolumn JC..DC z sufiksem -M/-W.")
                    return

                # wypełnij pudełka w zakładkach JUN-M i JUN-W
                filled_boxes = 0
                for key, nat_list in data_map.items():
                    t = self.quota_tables.get(key)
                    if t is None:
                        continue
                    try:
                        
                        df_view = pd.DataFrame({"Kraj": nat_list})
                        t.set_dataframe(df_view)
                        # kosmetyka nagłówka/kolumny
                        try:
                            tv = t.tree
                            tv.heading("Kraj", text="Kraj")
                            tv.column("Kraj", width=200, minwidth=140, stretch=True, anchor="w")
                        except Exception:
                            pass
                        filled_boxes += 1
                    except Exception:
                        pass

                # spróbuj odświeżyć „Wybór-JUN”, jeśli istnieje
                try:
                    # w Twoim kodzie ta funkcja jest lokalna – spróbuj ją odnaleźć przez nazwy lub fallback
                    if "_wybor_jun_tbl_m" in self.__dict__ or "_wybor_jun_tbl_w" in self.__dict__:
                        # zbudowane jest _rebuild_wybor_jun w tej samej funkcji – wywołaj jeśli w zasięgu
                        try:
                            _rebuild_wybor_jun()
                        except Exception:
                            pass
                except Exception:
                    pass

                # komunikat na pasku
                try:
                    info_lbl.config(text=f"Wczytano juniorów z pliku ({filled_boxes} tabel).")
                except Exception:
                    pass

            except Exception as e:
                messagebox.showerror("Juniorzy – błąd", str(e))

        # --- toolbar do uzupełniania wg Klasyfikacji ---
        tools = ttk.Frame(parent)
        tools.pack(before=sub, fill=tk.X, padx=8, pady=(6,6))
        # — kompaktowy pasek, który mieści się także w "Combined" —
        btn_fill = ttk.Button(tools, text="Wypełnij wg Klasyfikacji", command=_apply_from_classif)
        btn_fill.pack(side=tk.LEFT)
        btn_jun = ttk.Button(
            tools,
            text="Wczytaj juniorów (S45)",
            command=lambda: _fill_junior_quotas_from_file("S45/Juniorzy S45.csv")
        )
        btn_jun.pack(side=tk.LEFT, padx=(0,0))
    # === AUTOWYBÓR Z KWOT — COMPACT LOGIC ===
    def _reset_quota_memory(self):
        self._quota_used_count.clear()
        try:
            self.status.set("Reset pamięci kwot.")
        except Exception:
            pass

    def _sex_suffix(self) -> str:
        try:
            g = (self.var_f_gender.get() or "").strip().upper()
        except Exception:
            g = "M"
        return "W" if g == "W" else "M"

    def _table_to_df(self, table_widget):
        
        tv = getattr(table_widget, "tree", None) or getattr(table_widget, "Tree", None)
        if tv is None:
            return pd.DataFrame(columns=["Pozycja","Ilość"])
        cols = list(tv["columns"])
        out = []
        for iid in tv.get_children(""):
            item = tv.item(iid)
            row = {"Pozycja": item.get("text", "")}
            for c, v in zip(cols, item.get("values", [])):
                row[str(c)] = v
            out.append(row)
        df = pd.DataFrame(out)
        if "Ilość" in df.columns:
            df["Ilość"] = pd.to_numeric(df["Ilość"], errors="coerce").fillna(0).astype(int)
        return df

    def _compute_quota_map(self, tab_key: str):
        """
        Zwraca dict {NAT: ilosc} na podstawie tabeli 'Kwoty Startowe' dla klucza
        np. 'WC-M', 'COC-W', 'FC-M'. Wspiera:
        - numery miejsc (1,2,3,...)
        - kody krajów (AUT, CHN, ...)
        - 'Pozostali', 'Pozostali z pkt', 'Pozostali bez pkt'
        """
        # --- klasyfikacja krajów ---
        def _classif_nations_df(key: str) -> pd.DataFrame:
            # 0) najpewniejsze: z zakładki „Klasyfikacje”
            tab = getattr(self, "tab_klasyfikacje", None)
            if tab is not None and hasattr(tab, "get_nation_ranking"):
                try:
                    df = tab.get_nation_ranking(key)
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        return df
                except Exception:
                    pass
            # 1) ewentualne cache
            for attr in ("_classif_cache", "_klasyfikacje_cache", "_klasyf_df_cache"):
                cache = getattr(self, attr, None)
                if isinstance(cache, dict) and key in cache and isinstance(cache[key], pd.DataFrame):
                    df = cache[key]
                    if not df.empty:
                        return df
            return pd.DataFrame(columns=["NAT","PTS"])

        # --- DF kwot z widżetu ---
        def _quota_df(key: str) -> pd.DataFrame:
            # 0) dokładnie to, gdzie je zapisujesz przy budowie GUI
            qt = getattr(self, "quota_tables", None)
            if isinstance(qt, dict) and key in qt:
                try:
                    df = self._table_to_df(qt[key])
                    return df[["Pozycja","Ilość"]].copy()
                except Exception:
                    pass
            # 1) starsze aliasy – jeżeli jednak istnieją
            for attr in ("_quota_df_cache", "_kwoty_df_cache", "_kwoty_cache"):
                cache = getattr(self, attr, None)
                if isinstance(cache, dict) and key in cache and isinstance(cache[key], pd.DataFrame):
                    return cache[key]
            tv_map = getattr(self, "_quota_tree_widgets", None) or getattr(self, "_kwoty_tv", None)
            if isinstance(tv_map, dict) and key in tv_map:
                tv = tv_map[key]
                rows = []
                for iid in tv.get_children(""):
                    vals = list(tv.item(iid, "values"))
                    pos = vals[0] if len(vals) > 0 else tv.item(iid, "text")
                    qty = vals[1] if len(vals) > 1 else None
                    rows.append({"Pozycja": pos, "Ilość": qty})
                return pd.DataFrame(rows)
            return pd.DataFrame(columns=["Pozycja","Ilość"])

        def _nat_from_cell(s: str) -> str | None:
            if not isinstance(s, str):
                return None
            m = re.search(r"\b[A-Z]{3}\b", s.upper())
            return m.group(0) if m else None

        dfN = _classif_nations_df(tab_key).copy()
        if not dfN.empty:
            if "NAT" not in dfN.columns and "Nat" in dfN.columns: dfN.rename(columns={"Nat":"NAT"}, inplace=True)
            if "PTS" not in dfN.columns and "Points" in dfN.columns: dfN.rename(columns={"Points":"PTS"}, inplace=True)
            dfN["NAT"] = dfN["NAT"].astype(str).str.upper()
            dfN["PTS"] = pd.to_numeric(dfN["PTS"], errors="coerce").fillna(0)

        dfQ = _quota_df(tab_key).copy()

        # --- Letnie GP/SCOC: brak osobnych tabel kwot, więc licz z klasyfikacji ---
        key = (tab_key or "").strip().upper()
        # Rozbij: np. "GP-M" -> base="GP", sex="M"
        m = re.match(r"^([A-Z]+)-(M|W)$", key)
        base = m.group(1) if m else key
        sex  = m.group(2) if m else ""

        # LATO: używamy arkusza "Kwoty-LATO"; zima: "Kwoty Startowe"
        is_summer = base in ("GP","SCOC")
        sheet_name = "Kwoty-LATO" if is_summer else "Kwoty Startowe"

        # tag klasyfikacji do praw startów:
        # GP -> COC,  SCOC -> FC,  (zima bez zmian)
        if base == "GP":
            rights_tag = f"COC-{sex}" if sex else "COC"
        elif base == "SCOC":
            rights_tag = f"FC-{sex}" if sex else "FC"
        else:
            rights_tag = key  # WC/COC/FC itp. jak dotąd
        if dfQ.empty:
            base_tag = str(tab_key).split("-")[0].upper()
            if base_tag in ("GP", "SCOC"):
                dfN = _classif_nations_df(tab_key).copy()
                if not dfN.empty:
                    dfN = dfN.sort_values("PTS", ascending=False, kind="stable").reset_index(drop=True)
                    # tabela kwot GP/SCOC taka sama jak zimowa:
                    kwoty = [6,5,5,4,4,4,3,3,3,2,2,2]
                    mapping = {i+1: kwoty[i] if i < len(kwoty) else 1 for i in range(len(dfN))}
                    dfN["Kwota"] = dfN.index.map(lambda i: mapping.get(i+1, 1))
                    return dict(zip(dfN["NAT"], dfN["Kwota"]))
            # jeśli to nie GP/SCOC → stara logika
            return {}

        dfQ.rename(columns={dfQ.columns[0]: "Pozycja"}, inplace=True)
        if "Ilość" not in dfQ.columns: dfQ["Ilość"] = 0
        dfQ["Ilość"] = pd.to_numeric(dfQ["Ilość"], errors="coerce").fillna(0).astype(int)

        out, used = {}, set()
        nat_order = list(dfN["NAT"]) if not dfN.empty else []
        nat_pts   = dict(zip(dfN["NAT"], dfN["PTS"])) if not dfN.empty else {}

        # >>> NOWE: pełna pula krajów – ranking + baza zawodników (kraje bez punktów)
        try:
            all_nats = set(nat_order)
            all_nats |= set(self._all_known_countries())
        except Exception:
            all_nats = set(nat_order)
        all_nats_list = sorted(all_nats)

        def _is_zero_label(up: str) -> bool:
            # wyłap: "bez pkt", "bez pkt.", "bez punktów", "no pts", "no points" (z myślnikami/kropkami)
            up = re.sub(r'[\.\-_/]+', ' ', up)
            return bool(re.search(r'\bBEZ\s*(PKT|PUNKT)', up) or re.search(r'\bNO\s*(PTS|POINTS)\b', up))

        def _is_with_points_label(up: str) -> bool:
            up = re.sub(r'[\.\-_/]+', ' ', up)
            return bool(re.search(r'\bZ\s*(PKT|PUNKT)', up) or re.search(r'\bWITH\s*(PTS|POINTS)\b', up))

        def _add(nat, qty):
            if qty > 0 and nat:
                nat = str(nat).upper()
                out[nat] = out.get(nat, 0) + int(qty)
                used.add(nat)

        def _add(nat, qty):
            if qty > 0 and nat:
                nat = str(nat).upper()
                out[nat] = out.get(nat, 0) + int(qty)
                used.add(nat)

        for _, r in dfQ.iterrows():
            pos = str(r.get("Pozycja","")).strip()
            qty = int(r.get("Ilość", 0))
            if not pos or qty <= 0: 
                continue
            up = pos.upper()

            nat = _nat_from_cell(pos)
            if nat and nat != "POZOSTALI":
                _add(nat, qty); 
                continue

            if up.isdigit():
                i = int(up) - 1
                if 0 <= i < len(nat_order): _add(nat_order[i], qty)
                continue

            if "POZOSTALI" in up:
                # baza: wszyscy nieprzydzieleni, łącznie z krajami spoza klasyfikacji
                base_pool = [n for n in all_nats_list if n not in used]

                if _is_with_points_label(up):
                    # tylko ci, co mają >0 punktów w klasyfikacji
                    pool = [n for n in base_pool if nat_pts.get(n, 0) > 0]
                elif _is_zero_label(up):
                    # 0 pkt ORAZ ci, których w ogóle nie ma w klasyfikacji (traktuj jak 0)
                    pool = [n for n in base_pool if (n not in nat_pts) or (nat_pts.get(n, 0) == 0)]
                else:
                    # "Pozostali" (wszyscy nieprzydzieleni)
                    pool = base_pool

                for n in pool:
                    _add(n, qty)
                continue

        return out

    def _kwl_build_agg_df(self, key_a: str, key_b: str):
        
        qa = self._compute_quota_map(key_a) or {}
        qb = self._compute_quota_map(key_b) or {}
        countries = sorted(set(qa) | set(qb))
        rows = []
        for nat in countries:
            va = pd.to_numeric(qa.get(nat, 0), errors="coerce")
            vb = pd.to_numeric(qb.get(nat, 0), errors="coerce")
            a = int(0 if pd.isna(va) else va)
            b = int(0 if pd.isna(vb) else vb)
            rows.append({"Kraj": str(nat).upper(), "GP": a, "SCOC": b})
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["Kraj"], ascending=[True], kind="stable").reset_index(drop=True)
        return df

    def _refresh_kwoty_lato_aggregates(self):
        try:
            dfm = self._kwl_build_agg_df("GP-M", "SCOC-M")
            dfw = self._kwl_build_agg_df("GP-W", "SCOC-W")
        except Exception:
            
            dfm = pd.DataFrame(columns=["Kraj","GP","SCOC"])
            dfw = pd.DataFrame(columns=["Kraj","GP","SCOC"])
        try:
            if hasattr(self, "_kwl_agg_m"): self._kwl_agg_m.set_dataframe(dfm)
        except Exception:
            pass
        try:
            if hasattr(self, "_kwl_agg_w"): self._kwl_agg_w.set_dataframe(dfw)
        except Exception:
            pass

    def _ability_score(self, df):
        um = pd.to_numeric(df.get("UM", 50), errors="coerce").fillna(50)
        fo = pd.to_numeric(df.get("Forma", 50), errors="coerce").fillna(50)
        return 0.65*um + 0.35*fo

    def _all_known_countries(self):
        seen = set()

        # 1) Kraje z bazy zawodników
        df = getattr(self, "_roster_df_cache", None)
        if isinstance(df, pd.DataFrame) and "Kraj" in df.columns:
            seen |= set(df["Kraj"].astype(str))

        # 2) Kraje z zakładki „Klasyfikacje” (players/nations)
        tab = getattr(self, "tab_klasyfikacje", None)
        if tab is not None:
            for blob in getattr(tab, "sheet_data", {}).values():
                for key in ("players", "nations"):
                    dfk = (blob or {}).get(key)
                    if isinstance(dfk, pd.DataFrame) and "NAT" in dfk.columns:
                        seen |= set(dfk["NAT"].astype(str))

        # 3) Normalizacja – tylko czyste 3-literowe kody A–Z
        out = []
        for x in seen:
            s = str(x).upper()
            m = re.search(r"\b[A-Z]{3}\b", s)
            if m:
                out.append(m.group(0))

        return sorted(dict.fromkeys(out))

    def _get_pool_for_comp(self, comp_base: str, sex: str):
        
        pool = getattr(self, "_roster_df_filtered", None)
        if pool is None or pool.empty:
            pool = getattr(self, "_roster_df_cache", pd.DataFrame()).copy()
        pool = pool.copy()
        if "Płeć" in pool.columns and sex in ("M","W"):
            pool = pool[pool["Płeć"].astype(str).str.upper().eq(sex)]
        if "Kontuzja" in pool.columns:
            k = pd.to_numeric(pool["Kontuzja"], errors="coerce").fillna(0).astype(int)
            pool = pool[k.eq(0)]
        for c in ("Zawodnik","Kraj","UM","Forma"):
            if c not in pool.columns:
                pool[c] = "" if c in ("Zawodnik","Kraj") else 50
        pool["__ability"] = self._ability_score(pool)
        return pool
    # ============================================
    def _clear_filters(self):
        # wartości domyślne
        self.var_f_gender.set("WSZYSCY")
        self.var_f_level.set("WSZYSCY")
        self.var_f_countries.set("")
        self.var_f_age_min.set(""); self.var_f_age_max.set("")
        self.var_f_um_min.set(""); self.var_f_forma_min.set("")
        self.var_f_ps_only.set(False); self.var_f_healthy_only.set(False)
        self.var_f_search.set("")
        # odśwież widok
        self._refresh_roster_tab()

    def _filter_df_by_ui(self, df):
        

        out = df.copy()
        if out.empty:
            return out

        # a) Płeć
        if "Płeć" in out.columns:
            g = (self.var_f_gender.get() or "WSZYSCY").upper()
            if g in ("M","W"):
                out = out[out["Płeć"].astype(str).str.upper() == g]

        # b) JUN/SEN
        if "JUN/SEN" in out.columns:
            lv = (self.var_f_level.get() or "WSZYSCY").upper()
            if lv in ("JUN","SEN"):
                out = out[out["JUN/SEN"].astype(str).str.upper() == lv]

        # c) Kraje (kody rozdzielone przecinkami)
        if "Kraj" in out.columns:
            raw = (self.var_f_countries.get() or "").strip()
            if raw:
                toks = [t.strip().upper() for t in raw.split(",") if t.strip()]
                if toks:
                    out = out[out["Kraj"].astype(str).str.upper().isin(toks)]

        # d) Wiek min/max
        if "Wiek" in out.columns:
            try:
                amin = int(self.var_f_age_min.get() or 0)
            except:
                amin = 0
            try:
                amax = int(self.var_f_age_max.get() or 0)
            except:
                amax = 0
            if amin > 0:
                out = out[pd.to_numeric(out["Wiek"], errors="coerce").fillna(0) >= amin]
            if amax > 0:
                out = out[pd.to_numeric(out["Wiek"], errors="coerce").fillna(0) <= amax]

        # e) UM/Forma min
        if "UM" in out.columns:
            try:
                um_min = float(self.var_f_um_min.get() or 0)
            except:
                um_min = 0
            if um_min > 0:
                out = out[pd.to_numeric(out["UM"], errors="coerce").fillna(0) >= um_min]

        if "Forma" in out.columns:
            try:
                f_min = float(self.var_f_forma_min.get() or 0)
            except:
                f_min = 0
            if f_min > 0:
                out = out[pd.to_numeric(out["Forma"], errors="coerce").fillna(0) >= f_min]

        # f) PrawoStartu
        if self.var_f_ps_only.get() and "PrawoStartu" in out.columns:
            out = out[pd.to_numeric(out["PrawoStartu"], errors="coerce").fillna(0) >= 1]

        # g) Kontuzja
        if self.var_f_healthy_only.get() and "Kontuzja" in out.columns:
            out = out[pd.to_numeric(out["Kontuzja"], errors="coerce").fillna(0) == 0]

        # h) Szukaj w nazwisku
        q = (self.var_f_search.get() or "").strip().lower()
        if q and "Zawodnik" in out.columns:
            out = out[out["Zawodnik"].astype(str).str.lower().str.contains(q)]

        if "Kontuzja" in out.columns:
            k = pd.to_numeric(out["Kontuzja"], errors="coerce").fillna(0).astype(int)
            out = out[k.eq(0)]

        # ===== Prawo Startu – filtr pod konkretne zawody =====
        comp_raw = (getattr(self, "var_f_comp", None).get() if hasattr(self, "var_f_comp") else "WSZYSCY") or "WSZYSCY"
        use_rules = bool(getattr(self, "var_f_use_ps_rules", None).get() if hasattr(self, "var_f_use_ps_rules") else True)
        season_ref_str = (getattr(self, "var_f_ref_season", None).get() if hasattr(self, "var_f_ref_season") else "").strip()

        def _norm_comp(s):
            s = (s or "").strip().upper()
            m = {
                "PS": "WC", "PŚ": "WC", "WC": "WC",
                "LGP": "GP", "GP": "GP",
                "COC": "COC",
                "FC": "FC",
                "SCOC": "SCOC",
                "JUN": "JUN"
            }
            return m.get(s, "ALL")

        comp = _norm_comp(comp_raw)
        if comp != "ALL" and "PrawoStartu" in out.columns:
            ps = pd.to_numeric(out["PrawoStartu"], errors="coerce").fillna(0).astype(int)

            # wiek / JUN-SEN
            if "Wiek" in out.columns:
                age = pd.to_numeric(out["Wiek"], errors="coerce").fillna(0).astype(int)
                age_ok_jun = (age <= 14)
                age_ok_sen = (age >= 15)
            else:
                # fallback przez JUN/SEN
                lvl = out.get("JUN/SEN", "").astype(str).str.upper()
                age_ok_jun = lvl.eq("JUN")  # brak kolumny -> wszystko False
                age_ok_sen = lvl.eq("SEN")

            # dozwolone klasy wg zawodów
            allowed = {
                "WC":  {1, 2, 3},
                "COC": set(range(1, 7)),   # 1–6
                "FC":  set(range(1, 8)),   # 1–7
                "GP":  set(range(1, 7)),   # 1–6
                "SCOC": set(range(1, 8)),  # 1–7
                "JUN": {8},
            }[comp]

            # filtr klas
            cls_ok = ps.isin(allowed)

            # filtr wieku (JUN vs pozostałe)
            if comp == "JUN":
                age_ok = age_ok_jun
            else:
                age_ok = age_ok_sen

            mask = cls_ok & age_ok

            # --- reguły czasu trwania (opcjonalnie) ---
            if use_rules:
                # parse sezonu referencyjnego: "2025/26" -> 2025; "2025" -> 2025
                def _parse_season_start(s):
                    s = str(s or "").strip()
                    m = re.match(r"^\s*(\d{4})(?:/\d{2})?\s*$", s)
                    return int(m.group(1)) if m else None

                ref_year = _parse_season_start(season_ref_str)

                # kolumna sezonu nadania – spróbuj specyficznej dla zawodów, potem ogólnych:
                season_cols = [f"{comp}_SezonStart", "PrawoStartuSezon", "SezonStart", "Sezon"]

                # wsteczna zgodność dla WC/GP:
                if comp == "WC":
                    season_cols = ["WC_SezonStart", "PS_SezonStart", "PŚ_SezonStart", "SezonWC", "SezonPS"] + season_cols
                elif comp == "GP":
                    season_cols = ["GP_SezonStart", "LGP_SezonStart", "SezonGP", "SezonLGP"] + season_cols
                    
                season_cols = [f"{comp}_SezonStart", "PrawoStartuSezon", "SezonStart", "Sezon"]
                season_col = next((c for c in season_cols if c in out.columns), None)

                if ref_year is not None and season_col is not None:
                    start_y = out[season_col].apply(_parse_season_start)

                    # słownik długości ważności
                    # lifetime / this_and_next / this_only
                    dur = {}
                    if comp == "WC":
                        dur = {1: "lifetime", 2: "this_and_next", 3: "this_only"}
                    elif comp in ("COC", "GP"):
                        dur = {1: "lifetime", 2: "lifetime", 3: "lifetime", 4: "lifetime",
                            5: "this_and_next", 6: "this_only"}
                    elif comp in ("FC", "SCOC"):
                        dur = {k: "lifetime" for k in allowed}

                    def _valid(row_cls, row_start):
                        # JUN kontroluje już wiek; czasu trwania nie stosujemy
                        if comp == "JUN":
                            return True
                        rule = dur.get(int(row_cls), None)
                        if rule in (None, "lifetime"):
                            return True
                        if row_start is None:
                            return True  # brak danych o sezonie nadania → nie wykluczaj
                        delta = ref_year - int(row_start)
                        if rule == "this_and_next":
                            return (delta >= 0) and (delta <= 1)
                        if rule == "this_only":
                            return (delta == 0)
                        return True

                    dur_ok = [ _valid(c, y) for c, y in zip(ps.tolist(), start_y.tolist()) ]
                    mask = mask & pd.Series(dur_ok, index=out.index).astype(bool)

            out = out[mask]

        return out

    def _get_jun_countries(self, sex: str) -> list[str]:
        """
        Zwraca posortowaną listę unikalnych krajów z ośmiu pudełek JUN (JC..DC) dla danej płci.
        Próbuje najpierw zrzucić tabelę do DF (kolumna 'Kraj'), a jeśli się nie da, czyta #0 (text) z treeview.
        """
        tags = ["JC","MC","PC","QC","TC","AC","BC","DC"]
        out = []
        qt = getattr(self, "quota_tables", {}) or {}
        for t in tags:
            key = f"{t}-{sex}"
            tbl = qt.get(key)
            if not tbl:
                continue

            # spróbuj przez _table_to_df → kolumna 'Kraj'
            try:
                df = self._table_to_df(tbl)
                if "Kraj" in df.columns:
                    out.extend(df["Kraj"].dropna().astype(str).str.upper().str.strip().tolist())
                    continue
            except Exception:
                pass

            # fallback: czytaj z widgetu (tekst w #0)
            tv = getattr(tbl, "tree", None)
            if tv is not None:
                for iid in tv.get_children(""):
                    item = tv.item(iid)
                    txt = str(item.get("text", "")).strip().upper()
                    if txt:
                        out.append(txt)

        return sorted({x for x in out if x})

    def _jun_comp_for_nat(self, sex: str, nat: str) -> str:
        """
        Zwraca np. 'JC-M' / 'PC-W' dla kraju `nat` (kod 3-lit.) i płci `sex`,
        sprawdzając tabele JUN: JC, MC, PC, QC, TC, AC, BC, DC.
        Gdy kraj nie zostanie znaleziony, zwraca 'JUN-{sex}'.
        """
        nat = str(nat).strip().upper()
        qt = getattr(self, "quota_tables", {}) or {}

        def _codes_in_table(tbl) -> set[str]:
            # spróbuj zrzucić do DF
            try:
                df = self._table_to_df(tbl)
                if "Kraj" not in df.columns and "Pozycja" in df.columns:
                    df = df.rename(columns={"Pozycja": "Kraj"})
                if "Kraj" in df.columns:
                    return set(df["Kraj"].dropna().astype(str).str.upper().str.strip().tolist())
            except Exception:
                pass
            # fallback: odczyt z Treeview
            tv = getattr(tbl, "tree", None)
            if tv is not None:
                out = []
                for iid in tv.get_children(""):
                    item = tv.item(iid)
                    # w JUN mamy 1 kolumnę "Kraj" – bywa też w polu text
                    vals = item.get("values", [])
                    if vals:
                        out.append(str(vals[0]).strip().upper())
                    else:
                        out.append(str(item.get("text","")).strip().upper())
                return set(x for x in out if x)
            return set()

        for prefix in ["JC","MC","PC","QC","TC","AC","BC","DC"]:
            key = f"{prefix}-{sex}"
            tbl = qt.get(key)
            if not tbl:
                continue
            if nat in _codes_in_table(tbl):
                return key
        return f"JUN-{sex}"

    def _players_from_jun_countries(self, sex: str, per_country: int = 3):
        df_full = getattr(self, "_roster_df_cache", None)
        if df_full is None or df_full.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        # >>> KLUCZOWA ZMIANA: bierzemy unię krajów z JC..DC
        nats = self._get_jun_countries(sex)
        if not nats:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        base = df_full.copy()
        if "Płeć" in base.columns:
            base = base[base["Płeć"].astype(str).str.upper() == sex]

        pool = self._filter_df_for_comp_sex(base, "JUN", sex).copy()
        if pool.empty:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        # Wiek z 'Wiek' albo liczony z 'Rok ur.'
        if "Wiek" not in pool.columns:
            if "Rok ur." in pool.columns:
                pool["Wiek"] = date.today().year - pd.to_numeric(pool["Rok ur."], errors="coerce")
            else:
                pool["Wiek"] = pd.NA

        um    = pd.to_numeric(pool.get("UM", 50), errors="coerce").fillna(50)
        forma = pd.to_numeric(pool.get("Forma", 50), errors="coerce").fillna(50)
        pool["__ability"] = 0.65*um + 0.35*forma

        rows = []
        for nat in nats:
            cand = pool[pool["Kraj"].astype(str).str.upper() == nat].copy()
            if cand.empty:
                continue
            top = cand.sort_values("__ability", ascending=False, kind="mergesort").head(int(per_country))
            if not top.empty:
                comp_name = self._jun_comp_for_nat(sex, nat)
                rows.append(top.assign(Zawody=comp_name)[["Zawodnik","Kraj","Wiek","Zawody","UM","Forma"]])

        if not rows:
            return pd.DataFrame(columns=["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"])

        res = pd.concat(rows, ignore_index=True)
        res.insert(0, "Lp.", range(1, len(res)+1))
        return res[["Lp.","Zawodnik","Kraj","Wiek","Zawody","UM","Forma"]]

    def _build_preview(self, parent):
        paned = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        lf1 = Labeled(paned, "Klasyfikacja kwal.")
        lf2 = Labeled(paned, "Klasyfikacja końcowa")
        paned.add(lf1, weight=1)
        paned.add(lf2, weight=1)

        self.qual_tree = FrozenFirstColTable(lf1.body, frozen_col="Miejsce")
        self.qual_tree.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        self.qual_tree.pack(fill=tk.BOTH, expand=True)
        self.final_tree = FrozenFirstColTable(lf2.body, frozen_col="Miejsce")
        self.final_tree.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        self.final_tree.pack(fill=tk.BOTH, expand=True)

        # --- [NOWE] Pasek: aktualizacja klasyfikacji z Podglądu ---
        bar_cls = ttk.Frame(parent)
        bar_cls.pack(fill=tk.X, padx=8, pady=(0, 8))

        ttk.Label(bar_cls, text="Sezon:").pack(side=tk.LEFT)
        self._cls_season_var = tk.StringVar(value="S45")
        ttk.Entry(bar_cls, textvariable=self._cls_season_var, width=6).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(bar_cls, text="Cykl:").pack(side=tk.LEFT)
        _CLS_CYCLES = [
            "GP-M","SCOC-M","GP-W","SCOC-W",
            "SKI_FLYING_M","WC-M","COC-M","FC-M",
            "SKI_FLYING_W","WC-W","COC-W","FC-W",
            "JC-M","JC-W","MC-M","MC-W","PC-M","PC-W",
            "QC-M","QC-W","TC-M","TC-W","AC-M","AC-W",
            "BC-M","BC-W","DC-M","DC-W",
        ]
        self._cls_cycle_var = tk.StringVar(value="WC-M")
        self._cls_cycle_cb = ttk.Combobox(
            bar_cls, textvariable=self._cls_cycle_var,
            values=_CLS_CYCLES, width=14, state="readonly"
        )
        self._cls_cycle_cb.pack(side=tk.LEFT, padx=(4, 4))
        def _cls_cycle_prev():
            vals = list(self._cls_cycle_cb["values"])
            if not vals: return
            cur = self._cls_cycle_var.get()
            idx = vals.index(cur) if cur in vals else 0
            self._cls_cycle_var.set(vals[(idx - 1) % len(vals)])
        def _cls_cycle_next():
            vals = list(self._cls_cycle_cb["values"])
            if not vals: return
            cur = self._cls_cycle_var.get()
            idx = vals.index(cur) if cur in vals else -1
            self._cls_cycle_var.set(vals[(idx + 1) % len(vals)])
        ttk.Button(bar_cls, text="◀", width=2, command=_cls_cycle_prev).pack(side=tk.LEFT)
        ttk.Button(bar_cls, text="▶", width=2, command=_cls_cycle_next).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Button(
            bar_cls, text="Aktualizuj klasyfikacje…",
            command=lambda: self._on_update_classif_clicked(
                self._cls_season_var.get().strip(), self._cls_cycle_var.get().strip()
            )
        ).pack(side=tk.LEFT)
        ttk.Button(
            bar_cls, text="Aktualizuj rekordy życiowe",
            command=lambda: self._on_update_records_only_clicked(
                self._cls_season_var.get().strip()
            )
        ).pack(side=tk.LEFT, padx=(8, 0))

                # --- [NOWE] Pasek: klasyfikacje turniejów (TCS / RAW AIR / itd.) ---
        bar_tour = ttk.Frame(parent)
        bar_tour.pack(fill=tk.X, padx=8, pady=(0, 8))

        ttk.Label(bar_tour, text="Turniej:").pack(side=tk.LEFT)
        self._tour_code_var = tk.StringVar(value="TCS")
        ttk.Combobox(
            bar_tour,
            textvariable=self._tour_code_var,
            values=["TCS","FT","NT","WILLINGEN5","PLANICA7","RAWAIR-M","RAWAIR-W","BB"],
            width=12,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(bar_tour, text="Sesja (Q/K):").pack(side=tk.LEFT)
        self._tour_stage_var = tk.StringVar(value="K1")
        ttk.Combobox(
            bar_tour,
            textvariable=self._tour_stage_var,
            values=["Q1","Q2","K1","K2","K3","K4"],
            width=5,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(bar_tour, text="Sezon:").pack(side=tk.LEFT)
        self._tour_season_var = tk.StringVar(value="S45")
        ttk.Entry(bar_tour, textvariable=self._tour_season_var, width=6).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Button(
            bar_tour,
            text="Aktualizuj klasyfikację turnieju…",
            command=lambda: self._on_update_tour_clicked(
                self._tour_season_var.get().strip(),
                self._tour_code_var.get().strip(),
                self._tour_stage_var.get().strip(),
            ),
        ).pack(side=tk.LEFT)

        # --- [ZAKTUALIZOWANE] Pasek: zapis wyników mistrzostw do CSV ---
        bar_champs = ttk.Frame(parent)
        bar_champs.pack(fill=tk.X, padx=8, pady=(0, 8))

        ttk.Label(bar_champs, text="Mistrzostwa:").pack(side=tk.LEFT)
        self._champs_season_var = tk.StringVar(value="S45")
        ttk.Entry(bar_champs, textvariable=self._champs_season_var, width=6).pack(side=tk.LEFT, padx=(4, 12))

        # 1. Nazwa zawodów
        self._champs_name_var = tk.StringVar()
        self._cb_ch_name = ttk.Combobox(bar_champs, textvariable=self._champs_name_var, width=15, state="readonly")
        self._cb_ch_name["values"] = (
            "OG", "WCH", "SFWC", "JWC", "YOG", "UNI", "NKIC", "IST", 
            "COCH_EUROPE", "COCH_ASIA", "COCH_NORTHAMERICA", "COCH_SOUTHAMERICA", "COCH_AFRICA", "COCH_OCEANIA"
        )
        self._cb_ch_name.current(0)
        self._cb_ch_name.pack(side=tk.LEFT, padx=2)

        # 2. Płeć
        self._champs_sex_var = tk.StringVar()
        self._cb_ch_sex = ttk.Combobox(bar_champs, textvariable=self._champs_sex_var, width=3, state="readonly")
        self._cb_ch_sex["values"] = ("M", "W", "X")
        self._cb_ch_sex.current(0)
        self._cb_ch_sex.pack(side=tk.LEFT, padx=2)

        # 3. Typ (Q/IND/TEAM)
        self._champs_type_var = tk.StringVar()
        self._cb_ch_type = ttk.Combobox(bar_champs, textvariable=self._champs_type_var, width=6, state="readonly")
        self._cb_ch_type["values"] = ("Q", "IND", "TEAM")
        self._cb_ch_type.current(0)
        self._cb_ch_type.pack(side=tk.LEFT, padx=2)

        # 4. Skocznia (NORMAL/LARGE/puste)
        self._champs_hill_var = tk.StringVar()
        self._cb_ch_hill = ttk.Combobox(bar_champs, textvariable=self._champs_hill_var, width=8, state="readonly")
        self._cb_ch_hill["values"] = ("NORMAL", "LARGE", "")
        self._cb_ch_hill.current(0)
        self._cb_ch_hill.pack(side=tk.LEFT, padx=2)

        ttk.Button(
            bar_champs,
            text="Zapisz Q → CSV",
            command=lambda: self._export_champs_results("QUAL"),
        ).pack(side=tk.LEFT, padx=(10, 4))

        self._champs_ko64_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar_champs,
            text="KO64",
            variable=self._champs_ko64_var,
        ).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Button(
            bar_champs,
            text="Zapisz IND → CSV",
            command=lambda: self._export_champs_results("FINAL"),
        ).pack(side=tk.LEFT, padx=(4, 0))


    def _build_ko_tabs(self):
        # KO50 – Pary (R1)
        frame50 = Labeled(self.tab_ko50_pairs, "KO 50 – Pary (R1)")
        frame50.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ko50_body = frame50.body                    # 👈 zapisz body
        self.ko50_tree = Table(self.ko50_body)
        self.ko50_tree.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        self.ko50_tree.pack(fill=tk.BOTH, expand=True)

        # KO – Lucky Losers
        frameLL = Labeled(self.tab_ko_ll, "KO – Lucky Losers")
        frameLL.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ko_ll_body = frameLL.body                   # 👈 zapisz body
        self.ko_ll_tree = Table(self.ko_ll_body)
        self.ko_ll_tree.enable_flags_after_name(FLAGS_DIR, "Kraj")
        self.ko_ll_tree.pack(fill=tk.BOTH, expand=True)

        # KO64 – Drabinka (tabela)
        frame64tbl = Labeled(self.tab_ko64_bracket_tbl, "KO64 – Drabinka (tabela)")
        frame64tbl.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ko64_bracket_table_body = frame64tbl.body
        self.ko64_bracket_tree = Table(self.ko64_bracket_table_body)
        self.ko64_bracket_tree.enable_flags_after_name(FLAGS_DIR, "Kraj")
        self.ko64_bracket_tree.pack(fill=tk.BOTH, expand=True)

        # KO64 – Drabinka (grafika)
        frame64 = Labeled(self.tab_ko64_bracket, "KO64 – Drabinka (grafika)")
        frame64.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ko64_bracket = BracketCanvas(frame64.body)
        self.ko64_bracket.pack(fill=tk.BOTH, expand=True)

        # Upadki (bez zmian)
        frameF = Labeled(self.tab_falls, "Upadki – KO rundy + kwal.")
        frameF.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.falls_body = frameF.body
        self.falls_tree = FrozenFirstColTable(self.falls_body, frozen_col="Runda")
        self.falls_tree.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        self.falls_tree.pack(fill=tk.BOTH, expand=True)
        
    def _build_ko64_klasyfikacja(self, parent):
        """Zakładka z KO64 – Klasyfikacja (Odl1..Odl6 + Punkty)"""
        frame64k = Labeled(parent, "KO64 – Klasyfikacja (Odl1..Odl6 + Punkty)")
        frame64k.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ko64_klasyf_tree = FrozenFirstColTable(frame64k.body, frozen_col="Miejsce")
        self.ko64_klasyf_tree.enable_flags_after_name(FLAGS_DIR, "Kraj", "Zawodnik")
        self.ko64_klasyf_tree.pack(fill=tk.BOTH, expand=True)
    # ------- callbacks / utilities -------
    # ——— Kalendarz cyklu – metody pomocnicze ———

    def _pick_calendar_csv(self):
        """Otwórz dialog wyboru pliku kalendarza cyklu."""
        path = filedialog.askopenfilename(
            title="Wybierz plik kalendarza cyklu (CSV)",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")]
        )
        if path:
            self.var_calendar_csv.set(path)
            self._load_calendar_csv()

    def _load_calendar_csv(self):
        """Wczytaj kalendarz cyklu i ogranicz combobox skoczni do skoczni z kalendarza (w kolejności tygodniowej)."""
        path = self.var_calendar_csv.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Kalendarz", f"Nie znaleziono pliku: {path}")
            return
        try:
            # utf-8-sig usuwa BOM (efbbbf) który Excel dodaje przy zapisie CSV
            try:
                df_cal = pd.read_csv(path, sep=";", encoding="utf-8-sig")
            except Exception:
                try:
                    df_cal = pd.read_csv(path, sep=";", encoding="cp1250")
                except Exception:
                    df_cal = pd.read_csv(path, sep=";")
        except Exception as e:
            messagebox.showerror("Kalendarz", f"Błąd wczytywania kalendarza: {e}")
            return

        # Sprawdź wymagane kolumny
        required = {"WEEK", "NAT", "Skocznia", "HS"}
        if not required.issubset(set(df_cal.columns)):
            messagebox.showerror("Kalendarz", f"Plik kalendarza musi mieć kolumny: {required}\nZnaleziono: {list(df_cal.columns)}")
            return

        self._calendar_df = df_cal.copy()

        # Wywołaj filtrowanie (wymaga wcześniej wczytanej listy skoczni)
        if not hasattr(self, "_hills_df") or self._hills_df is None or self._hills_df.empty:
            messagebox.showinfo("Kalendarz",
                "Kalendarz wczytany. Teraz wczytaj plik skoczni (Wczytaj), "
                "a combobox zostanie automatycznie przefiltrowany.")
            return
        self._apply_calendar_filter()

    def _apply_calendar_filter(self):
        """Ogranicz combobox do skoczni z kalendarza, posortowanych wg tygodnia."""
        if self._calendar_df is None or not hasattr(self, "_hills_df") or self._hills_df is None:
            return

        df_cal = self._calendar_df.copy()
        df_cal["HS_num"] = pd.to_numeric(
            df_cal["HS"].astype(str).str.replace("HS", "", regex=False), errors="coerce"
        )
        df_cal["WEEK_num"] = pd.to_numeric(df_cal["WEEK"], errors="coerce")
        df_cal = df_cal.dropna(subset=["HS_num", "WEEK_num"]).copy()

        # Unikalne skocznie z kalendarza w kolejności tygodniowej (pierwsza wizyta)
        seen = {}
        for _, r in df_cal.sort_values("WEEK_num").iterrows():
            skocznia = str(r["Skocznia"]).strip()
            hs = int(r["HS_num"])
            key = (skocznia.lower(), hs)
            if key not in seen:
                seen[key] = {"skocznia": skocznia, "hs": hs, "week": int(r["WEEK_num"]), "nat": str(r.get("NAT","")).strip()}

        ordered_keys = list(seen.keys())  # w kolejności tygodniowej

        # Dopasuj do _hills_df (szukamy po HS i nazwie miasta/skoczni)
        filtered_rows = []
        for key in ordered_keys:
            skocznia_cal, hs_cal = key
            # Szukaj w _hills_df pasującego wiersza
            mask = self._hills_df["HS_num"] == hs_cal
            candidates = self._hills_df[mask]
            if candidates.empty:
                continue
            # Spróbuj dopasować po nazwie skoczni lub miasta
            best = None
            for _, row in candidates.iterrows():
                miasto = str(row.get("Miasto","")).strip().lower()
                skocznia_db = str(row.get("Skocznia","")).strip().lower()
                if skocznia_cal in miasto or skocznia_cal in skocznia_db or \
                   miasto in skocznia_cal or skocznia_db in skocznia_cal:
                    best = row
                    break
            if best is None:
                # fallback: weź pierwszego kandydata z tym HS
                best = candidates.iloc[0]
            # Dodaj info o tygodniu do etykiety
            week_info = seen[key]["week"]
            label = best["__label"] + f"  [Tydzień {week_info}]"
            filtered_rows.append((label, best.name))  # name = indeks w _hills_df

        if not filtered_rows:
            messagebox.showwarning("Kalendarz",
                "Nie udało się dopasować żadnej skoczni z kalendarza do listy skoczni.\n"
                "Sprawdź, czy nazwy skoczni w kalendarzu pasują do pliku skoczni.")
            return

        # Zachowaj mapowanie label → indeks w _hills_df
        self._calendar_labels = [lbl for lbl, _ in filtered_rows]
        self._calendar_hill_indices = [idx for _, idx in filtered_rows]

        self.cbo_hill["values"] = self._calendar_labels
        self.cbo_hill.current(0)
        self._on_hill_selected()  # ustaw parametry dla pierwszej skoczni
        n = len(filtered_rows)
        self.log(f"[Kalendarz] Wczytano {n} skoczni z cyklu. Przełącz strzałkami ◀ ▶.")

    def _clear_calendar_filter(self):
        """Wyczyść filtr kalendarza – przywróć pełną listę skoczni."""
        self._calendar_df = None
        self._calendar_labels = None
        self._calendar_hill_indices = None
        self.var_calendar_csv.set("")
        if hasattr(self, "_hills_df") and self._hills_df is not None:
            self.cbo_hill["values"] = self._hills_df["__label"].tolist()
            self.log("[Kalendarz] Filtr wyczyszczony – wyświetlana pełna lista skoczni.")

    # ——— Filtr wg tygodnia (wszystkie cykle naraz) ———

    def _pick_calendars_dir(self):
        """Otwórz dialog wyboru folderu z plikami kalendarzy CSV."""
        path = filedialog.askdirectory(title="Wybierz folder z plikami kalendarzy CSV")
        if path:
            self.var_calendars_dir.set(path)
            self._load_calendars_dir()

    def _load_calendars_dir(self):
        """Wczytaj wszystkie pliki Kalendarz_*.csv z folderu i zbuduj listę tygodni."""
        folder = self.var_calendars_dir.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Tygodnie", f"Nie znaleziono folderu: {folder}")
            return

        import glob
        files = sorted(glob.glob(os.path.join(folder, "Kalendarz_*.csv")))
        if not files:
            messagebox.showerror("Tygodnie",
                f"Nie znaleziono plików Kalendarz_*.csv w folderze:\n{folder}")
            return

        frames = []
        for fpath in files:
            # Wyciągnij nazwę cyklu z nazwy pliku, np. Kalendarz_S45_JC-M.csv → JC-M
            fname = os.path.basename(fpath)
            parts = fname.replace(".csv", "").split("_")
            cykl = parts[-1] if len(parts) >= 3 else fname
            try:
                try:
                    df = pd.read_csv(fpath, sep=";", encoding="utf-8-sig")
                except Exception:
                    try:
                        df = pd.read_csv(fpath, sep=";", encoding="cp1250")
                    except Exception:
                        df = pd.read_csv(fpath, sep=";")
            except Exception as e:
                self.log(f"[Tygodnie] Pominięto {fname}: {e}")
                continue

            # Normalizuj nazwę kolumny tygodnia
            df.columns = [c.strip() for c in df.columns]
            week_col = next((c for c in df.columns if c.upper() == "WEEK"), None)
            if week_col is None:
                self.log(f"[Tygodnie] Pominięto {fname}: brak kolumny WEEK")
                continue

            df = df.rename(columns={week_col: "WEEK"})
            df["WEEK"] = pd.to_numeric(df["WEEK"], errors="coerce")
            df = df.dropna(subset=["WEEK"]).copy()
            df["WEEK"] = df["WEEK"].astype(int)

            # Normalizuj HS
            if "HS" in df.columns:
                df["HS_num"] = pd.to_numeric(
                    df["HS"].astype(str).str.replace("HS", "", regex=False), errors="coerce"
                )
            else:
                df["HS_num"] = float("nan")

            df["__cykl"] = cykl
            frames.append(df)

        if not frames:
            messagebox.showerror("Tygodnie", "Żaden plik kalendarza nie zawierał danych.")
            return

        self._all_calendars_df = pd.concat(frames, ignore_index=True)

        # Wypełnij combobox tygodni
        weeks = sorted(self._all_calendars_df["WEEK"].unique())
        self.cbo_week["values"] = [str(w) for w in weeks]
        if weeks:
            self.cbo_week.current(0)
            self._on_week_selected()
        n_cykli = self._all_calendars_df["__cykl"].nunique()
        self.log(f"[Tygodnie] Wczytano {len(files)} plików ({n_cykli} cykli), tygodnie: {weeks[0]}–{weeks[-1]}")

    def _on_week_selected(self, *_):
        """Po wyborze tygodnia – ogranicz combobox skoczni do zawodów z tego tygodnia."""
        if self._all_calendars_df is None:
            return
        try:
            week = int(self.var_week_pick.get())
        except ValueError:
            return

        week_df = self._all_calendars_df[self._all_calendars_df["WEEK"] == week].copy()
        if week_df.empty:
            self.log(f"[Tygodnie] Brak zawodów w tygodniu {week}")
            return

        # Usuń duplikaty tej samej skoczni+HS+cykl (zostawiamy pierwsze wystąpienie)
        week_df = week_df.drop_duplicates(subset=["__cykl", "Skocznia", "HS_num"])

        # Posortuj wg hierarchii cykli
        hierarchy = [
            "WC-M","WC-W","GP-M","GP-W","SCOC-M","SCOC-W",
            "COC-M","COC-W","FC-M","FC-W",
            "JC-M","JC-W","MC-M","MC-W","PC-M","PC-W",
            "QC-M","QC-W","TC-M","TC-W","AC-M","AC-W",
            "BC-M","BC-W","DC-M","DC-W",
        ]
        def _rank(cykl):
            try: return hierarchy.index(cykl)
            except ValueError: return len(hierarchy)
        week_df["__rank"] = week_df["__cykl"].apply(_rank)
        week_df = week_df.sort_values("__rank").reset_index(drop=True)

        if not hasattr(self, "_hills_df") or self._hills_df is None or self._hills_df.empty:
            messagebox.showinfo("Tygodnie",
                "Najpierw wczytaj plik skoczni (przycisk 'Wczytaj' przy 'Plik skoczni').")
            return

        # Dopasuj każdą pozycję tygodnia do wiersza w _hills_df
        filtered_rows = []
        for _, r in week_df.iterrows():
            skocznia_cal = str(r.get("Skocznia", "")).strip().lower()
            hs_cal = r.get("HS_num", float("nan"))
            cykl = str(r.get("__cykl", "")).strip()
            if pd.isna(hs_cal):
                continue

            candidates = self._hills_df[self._hills_df["HS_num"] == int(hs_cal)]
            if candidates.empty:
                continue

            best = None
            for _, row in candidates.iterrows():
                miasto = str(row.get("Miasto", "")).strip().lower()
                skocznia_db = str(row.get("Skocznia", "")).strip().lower()
                if (skocznia_cal in miasto or skocznia_cal in skocznia_db or
                        miasto in skocznia_cal or skocznia_db in skocznia_cal):
                    best = row
                    break
            if best is None:
                best = candidates.iloc[0]

            label = f"[{cykl}] {best['__label']}"
            filtered_rows.append((label, best.name))

        if not filtered_rows:
            self.log(f"[Tygodnie] Tydzień {week}: nie dopasowano żadnej skoczni.")
            return

        self._calendar_labels = [lbl for lbl, _ in filtered_rows]
        self._calendar_hill_indices = [idx for _, idx in filtered_rows]
        # Wyłącz filtr cyklu jeśli był aktywny
        self._calendar_df = None

        self.cbo_hill["values"] = self._calendar_labels
        self.cbo_hill.current(0)
        self._on_hill_selected()
        self.log(f"[Tygodnie] Tydzień {week}: {len(filtered_rows)} skoczni.")

    def _week_prev(self):
        """Przejdź do poprzedniego tygodnia."""
        vals = self.cbo_week["values"]
        if not vals:
            return
        idx = self.cbo_week.current()
        idx = (idx - 1) % len(vals)
        self.cbo_week.current(idx)
        self._on_week_selected()

    def _week_next(self):
        """Przejdź do następnego tygodnia."""
        vals = self.cbo_week["values"]
        if not vals:
            return
        idx = self.cbo_week.current()
        idx = (idx + 1) % len(vals)
        self.cbo_week.current(idx)
        self._on_week_selected()

    def _clear_week_filter(self):
        """Wyczyść filtr tygodnia – przywróć pełną listę skoczni."""
        self._all_calendars_df = None
        self._calendar_labels = None
        self._calendar_hill_indices = None
        self.var_week_pick.set("")
        self.cbo_week["values"] = []
        if hasattr(self, "_hills_df") and self._hills_df is not None:
            self.cbo_hill["values"] = self._hills_df["__label"].tolist()
            self.log("[Tygodnie] Filtr wyczyszczony – wyświetlana pełna lista skoczni.")

    def _hill_prev(self):
        """Przejdź do poprzedniej skoczni na liście."""
        values = self.cbo_hill["values"]
        if not values:
            return
        idx = self.cbo_hill.current()
        if idx < 0:
            idx = 0
        else:
            idx = (idx - 1) % len(values)
        self.cbo_hill.current(idx)
        self._on_hill_selected()

    def _hill_next(self):
        """Przejdź do następnej skoczni na liście."""
        values = self.cbo_hill["values"]
        if not values:
            return
        idx = self.cbo_hill.current()
        if idx < 0:
            idx = 0
        else:
            idx = (idx + 1) % len(values)
        self.cbo_hill.current(idx)
        self._on_hill_selected()

    def _pick_hills_csv(self):
        path = filedialog.askopenfilename(
            title="Wybierz plik skoczni (CSV)",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")]
        )
        if path:
            self.var_hills_csv.set(path)
            self._load_hills_csv()

    def _load_hills_csv(self):
        """Wczytaj listę skoczni z CSV (sep=';' + cp1250) i zasil combobox."""
        path = self.var_hills_csv.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Skocznie", f"Nie znaleziono pliku: {path}")
            return
        try:
            df = pd.read_csv(path, sep=";", encoding="cp1250")
        except Exception:
            # fallback: standardowe kodowanie
            df = pd.read_csv(path, sep=";")

        # Upewnij się, że mamy kluczowe kolumny — w Twoim CSV są m.in.:
        # ['Reprezentacja','Kraj','Miasto','Skocznia','K','HS', ...]
        for col in ("Miasto","Skocznia","K","HS","Kraj"):
            if col not in df.columns:
                df[col] = ""

        # tylko wiersze z numerami K i HS
        df["K_num"]  = pd.to_numeric(df["K"], errors="coerce")
        df["HS_num"] = pd.to_numeric(df["HS"], errors="coerce")
        df = df.dropna(subset=["K_num","HS_num"]).copy()

        # Tekst do wyświetlenia
        def _lbl(r):
            miasto = str(r.get("Miasto","")).strip()
            k      = int(r.get("K_num", 0))
            hs     = int(r.get("HS_num", 0))
            kraj   = str(r.get("Kraj","")).strip().upper()
            core   = f"{miasto} (K{k}/HS{hs})".strip()
            return f"[{kraj}] {core}" if kraj else core

        df["__label"] = df.apply(_lbl, axis=1)

        # sort: kraj, miasto, HS malejąco (żeby HS większe były wyżej w tej samej lokalizacji)
        try:
            df = df.sort_values(["Kraj","Miasto","HS_num"], ascending=[True, True, False])
        except Exception:
            df = df.sort_values("__label")

        self._hills_df = df.reset_index(drop=True)

        # Jeśli załadowany jest kalendarz – zastosuj filtr; w przeciwnym razie pełna lista
        if hasattr(self, "_calendar_df") and self._calendar_df is not None:
            self._apply_calendar_filter()
        else:
            values = self._hills_df["__label"].tolist()
            self.cbo_hill["values"] = values
            # auto-wybór: jeśli w polu „Nazwa" coś mamy, spróbuj dopasować
            curr = (self.var_hill.get() or "").strip().lower()
            if curr:
                idx = next((i for i, s in enumerate(values) if curr in s.lower()), -1)
                if idx >= 0:
                    self.cbo_hill.current(idx)

    def _on_hill_selected(self, *_):
        """Po wyborze skoczni ustaw Nazwę/K/HS, a 'Punkty za metr' wyczyść (auto)."""
        try:
            idx = self.cbo_hill.current()
            if idx < 0:
                return
            # Jeśli aktywny filtr kalendarza – użyj mapowania na prawdziwy indeks w _hills_df
            if hasattr(self, "_calendar_hill_indices") and self._calendar_hill_indices is not None:
                hills_idx = self._calendar_hill_indices[idx]
                r = self._hills_df.loc[hills_idx]
            else:
                r = self._hills_df.iloc[idx]
            miasto = str(r.get("Miasto","")).strip()
            nazwa  = str(r.get("Skocznia","")).strip()
            hs     = int(r.get("HS_num", 0))
            k      = int(r.get("K_num", 0))

            # Przyjazna nazwa arkusza/pliku wynikowego
            pretty = f"{miasto} (K{k}/HS{hs})".strip()
            self.var_hill.set(pretty)

            self.var_k.set(k)
            self.var_hs.set(hs)
            # metry zostaw puste → silnik sam policzy sim.compute_meter_value(K)
            self.var_meter.set("")
        except Exception as e:
            messagebox.showerror("Skocznie", f"Nie udało się ustawić parametrów: {e}")

    def _on_cycle_selected(self, *_):
        """Auto-setup na podstawie wybranego cyklu i tygodnia."""
        import re as _re

        cycle = self.var_cycle.get().strip()
        if not cycle:
            return

        sex = "W" if cycle.endswith("-W") else "M"

        def _base(c):
            c = c.upper()
            for pfx in ("COCH-EU-","COCH-AS-","COCH-NA-","COCH-SA-","COCH-AF-","COCH-OC-"):
                if c.startswith(pfx):
                    return "COCH"
            return _re.sub(r"-[MW]$", "", c)

        base = _base(cycle)

        coch_region = ""
        m = _re.match(r"COCH-([A-Z]+)-[MW]$", cycle.upper())
        if m:
            coch_region = m.group(1)

        _CONT_MAP = {"EU":"Europe","AS":"Asia","NA":"North America",
                     "SA":"South America","AF":"Africa","OC":"Oceania"}
        coch_cont_full = _CONT_MAP.get(coch_region, "")

        try:
            week = int(self.var_week_pick.get().strip())
        except Exception:
            week = 0

        try:
            season_num = int(_re.search(r"\d+", self._cls_season_var.get()).group())
        except Exception:
            season_num = 0

        # a) filtr listy skoczni
        try:
            # zawsze filtrujemy z pelnej listy kalendarza, nie z aktualnych values
            source = getattr(self, "_calendar_labels", None) or list(self.cbo_hill["values"])
            tag_prefix = f"[{cycle}]"
            filtered = [lbl for lbl in source if lbl.startswith(tag_prefix)]
            # przywroc pelna liste (zeby kolejne wywolania dzialaly poprawnie)
            self.cbo_hill["values"] = source
            if filtered:
                self.cbo_hill.set(filtered[0])
                self._on_hill_selected()
        except Exception:
            pass

        # b) tryb zawodów
        def _set_mode(mode):
            self.var_classic.set(mode == "classic")
            self.var_ko50.set(mode == "ko50")
            self.var_ko64_full.set(mode == "ko64")

        if base == "IST":
            _set_mode("ko64")
        elif base == "WC" and week == 14:
            _set_mode("ko50")
        else:
            _set_mode("classic")

        # c) format
        try:
            hs = int(self.var_hs.get())
        except Exception:
            hs = 0

        if hs > 160:
            fmt = "Mamut  (40,30 / Q:40)"
        elif base == "FC":
            fmt = "Full  (999,30 / Q:999)"
        elif base == "NKIC":
            fmt = "NKIC  (64,32,16,8,4,2 / Q:64)"
        else:
            fmt = "Classic  (50,30 / Q:50)"

        self.var_format_preset.set(fmt)
        if fmt in self._format_presets:
            cuts, spots = self._format_presets[fmt]
            self.var_round_cuts.set(cuts)
            self.var_qual_spots.set(spots)

        # d) wyczyść listę startową
        try:
            self._roster_remove_all()
        except Exception:
            pass

        # e) nawigacja i selekcja
        def _switch_nb(nb, tab_text):
            try:
                for t in nb.tabs():
                    if nb.tab(t, "text") == tab_text:
                        nb.select(t)
                        return True
            except Exception:
                pass
            return False

        def _get_tbl(registry, key):
            val = registry.get(key)
            if isinstance(val, list):
                return val[0] if val else None
            return val

        def _select_in_tbl(tbl, comp_code):
            if tbl is None:
                return
            tv = getattr(tbl, "tv_main", getattr(tbl, "tree", None))
            if tv is None:
                return
            try:
                tv.selection_remove(tv.selection())
            except Exception:
                pass
            for iid in tv.get_children(""):
                try:
                    val = str(tv.set(iid, "Zawody")).strip().upper()
                    if val == comp_code.upper():
                        tv.selection_add(iid)
                except Exception:
                    pass
            try:
                sel = tv.selection()
                if sel:
                    tv.see(sel[0])
                tbl._sync_from_main(None)
            except Exception:
                pass

        def _transfer_tbl(tbl):
            if tbl is None:
                return
            tv = getattr(tbl, "tv_main", getattr(tbl, "tree", None))
            if tv is None:
                return
            try:
                df = self._tree_selection_to_df(tv, name_col=getattr(tbl, "_name_col", "Zawodnik"))
                self._add_players_to_startlist(df)
            except Exception:
                pass

        try:
            self.nb.select(self.tab_quotas)
        except Exception:
            pass

        nb_wybor = getattr(self, "_nb_wybor", None)
        nb_kwoty_sub = getattr(self, "_nb_kwoty_sub", None)

        if nb_kwoty_sub:
            _switch_nb(nb_kwoty_sub, "Wybór")

        if 1 <= week <= 6:
            if nb_wybor:
                _switch_nb(nb_wybor, "LATO")
            tbl = _get_tbl(getattr(self, "_wyborLATO_players", {}), sex)
            _select_in_tbl(tbl, base)
            _transfer_tbl(tbl)

        elif week in list(range(7, 8)) + list(range(10, 15)) + list(range(17, 20)) + list(range(29, 33)):
            if nb_wybor:
                _switch_nb(nb_wybor, "MEN" if sex == "M" else "WOMEN")
            tbl_list = getattr(self, "_wybor_players", {}).get(sex, [])
            tbl = tbl_list[0] if tbl_list else None
            _select_in_tbl(tbl, base)
            _transfer_tbl(tbl)

        elif 22 <= week <= 26:
            if nb_wybor:
                _switch_nb(nb_wybor, "MEN" if sex == "M" else "WOMEN")
            tbl_list = getattr(self, "_wybor_players", {}).get(sex, [])
            tbl = tbl_list[0] if tbl_list else None
            _select_in_tbl(tbl, base)
            _transfer_tbl(tbl)

        elif week == 9:
            if nb_wybor:
                _switch_nb(nb_wybor, "JWC")
            self._select_in_jwc_table(sex, base)
            self._move_selected_to_startlist(sex)

        elif week == 15:
            season_mod = season_num % 4
            if season_mod == 0:
                if nb_wybor:
                    _switch_nb(nb_wybor, "COCH")
                tbl = _get_tbl(getattr(self, "_wyborCOCH_players", {}), sex)
                if tbl and coch_cont_full:
                    tv = getattr(tbl, "tv_main", getattr(tbl, "tree", None))
                    if tv:
                        try:
                            tv.selection_set(())
                            for iid in tv.get_children():
                                if str(tv.set(iid, "Zawody")) == coch_cont_full:
                                    tv.selection_add(iid)
                        except Exception:
                            pass
                _transfer_tbl(tbl)
            elif season_mod == 1:
                if nb_wybor:
                    _switch_nb(nb_wybor, "YOG")
                tbl = _get_tbl(getattr(self, "_wyborYOG_players", {}), sex)
                _select_in_tbl(tbl, base)
                _transfer_tbl(tbl)
            elif season_mod == 2:
                if nb_wybor:
                    _switch_nb(nb_wybor, "UNI")
                tbl = _get_tbl(getattr(self, "_wyborUNI_players", {}), sex)
                _select_in_tbl(tbl, base)
                _transfer_tbl(tbl)
            else:
                if nb_wybor:
                    _switch_nb(nb_wybor, "CH")
                tbl_list = getattr(self, "_wyborCH_players", {}).get(sex, [])
                tbl = tbl_list[0] if tbl_list else None
                _select_in_tbl(tbl, "WC")
                _transfer_tbl(tbl)

        elif week in (21, 27):
            if nb_wybor:
                _switch_nb(nb_wybor, "CH")
            tbl_list = getattr(self, "_wyborCH_players", {}).get(sex, [])
            tbl = tbl_list[0] if tbl_list else None
            if base in ("OG","WCH","SFWC","NKIC","IST"):
                _select_in_tbl(tbl, "WC")
            else:
                _select_in_tbl(tbl, base)
            _transfer_tbl(tbl)

        # f) sortuj wg klasyfikacji (odwrotnie) dla cyklow rankingowych
        if base in ("WC","COC","FC","GP","SCOC"):
            try:
                gc_vals = list(self.gc_cycle_cb["values"])
                # szukamy np. "WC-M" w dostepnych cyklach klasyfikacji
                want = cycle  # np. "WC-M"
                if want in gc_vals:
                    self.var_gc_cycle.set(want)
                elif any(v.upper() == want.upper() for v in gc_vals):
                    match = next(v for v in gc_vals if v.upper() == want.upper())
                    self.var_gc_cycle.set(match)
                self._on_apply_gc_reverse()
            except Exception:
                pass

        # g) wróc do zakładki Parametry
        try:
            self.nb.select(self.tab_params)
        except Exception:
            pass

    def pick_excel(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("CSV", "*.csv"),
                ("Excel", "*.xlsx;*.xls"),
                ("Wszystkie pliki", "*.*"),
            ]
        )
        if path:
            self.var_excel.set(path)
            self._refresh_roster_tab()  # odśwież listy po wyborze pliku

    def pick_outdir(self):
        path = filedialog.askdirectory(title="Wybierz folder wyników")
        if path: self.var_outdir.set(path)

    def log(self, msg):
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    def set_busy(self, b):
        if b: self.status.set("Symulacja…"); self.pbar.start(60)
        else: self.status.set("Gotowy."); self.pbar.stop()

    def _limit_df(self, df, show_all, n):
        if df is None:
            return df
        if show_all:
            return df
        try:
            n = max(1, int(n))
        except Exception:
            n = 50
        return df.head(n)
    
    def _prepare_falls_df(self, df: pd.DataFrame) -> pd.DataFrame:
        

        if df is None or getattr(df, "empty", True):
            return pd.DataFrame(columns=["Runda", "Zawodnik", "Kraj", "Odległość"])

        out = df.copy()

        def _find_col(cols, names):
            names = [str(n).strip().lower() for n in (names if isinstance(names, (list, tuple)) else [names])]
            for c in cols:
                if str(c).strip().lower() in names:
                    return c
            return None

        col_round   = _find_col(out.columns, ["runda", "seria", "round", "phase"])
        col_name    = _find_col(out.columns, ["zawodnik", "name"])
        col_country = _find_col(out.columns, ["kraj", "country"])
        col_dist    = _find_col(out.columns, ["odległość", "odl.", "odl", "odl.1", "odl1", "odl.q", "odlq", "odl_runda"])

        if col_round is None:  out["Runda"] = "?"
        else:                  out.rename(columns={col_round: "Runda"}, inplace=True)

        if col_name is None:   out["Zawodnik"] = out.iloc[:, 0].astype(str)
        else:                  out.rename(columns={col_name: "Zawodnik"}, inplace=True)

        if col_country is None: out["Kraj"] = ""
        else:                    out.rename(columns={col_country: "Kraj"}, inplace=True)

        if col_dist is None:    out["Odległość"] = ""
        else:                    out.rename(columns={col_dist: "Odległość"}, inplace=True)

        want = ["Runda","Zawodnik","Kraj","Sex","Lekarz","Infrastruktura","Odległość"]
        for c in want:
            if c not in out.columns:
                out[c] = "" if c != "Odległość" else out.get("Odległość","")
        keep = [c for c in want if c in out.columns]
        return out[keep]

    def run_clicked(self):
        threading.Thread(target=self._run_safe, daemon=True).start()

    def _run_safe(self):
        try:
            self.set_busy(True)
            self._run()
        except Exception:
            self.log(traceback.format_exc())
            messagebox.showerror("Błąd", "Wystąpił błąd – szczegóły w logu.")
        finally:
            self.set_busy(False)

    def _run(self):
        kwal_df = pd.DataFrame()
        kval_rank = pd.DataFrame()
        contest_rows = pd.DataFrame()
        klasyf = pd.DataFrame()
        extra = {}
        ex = {}
        excel = self.var_excel.get().strip()
        outdir = self.var_outdir.get().strip() or "./wyniki"
        hill = self.var_hill.get().strip() or "Skocznia"
        k = int(self.var_k.get()); hs = int(self.var_hs.get())
        meter_str = self.var_meter.get().strip()
        meter = None if meter_str == "" else float(meter_str)

        wind_mean = float(self.var_wind_mean.get())
        wind_sd = float(self.var_wind_sd.get())
        wind_phi = float(self.var_wind_phi.get())
        takeoff_gain = float(self.var_wind_takeoff_gain.get())
        flight_gain = float(self.var_wind_flight_gain.get())
        gate = int(self.var_gate.get())
        p_gate = float(self.var_p_gate_change.get())
        max_gate = int(self.var_max_gate_delta.get())
        randomness = float(self.var_randomness.get())
        elite_regress = float(self.var_elite_regress.get())
        judges_rho = float(self.var_judges_rho.get())

        roster = sim.load_roster(Path(excel))
        # Jeśli korzystamy z listy startowej i jest NIEPARZYSTA – dodaj techniczne BYE,
        # żeby parowanie 2-osobowe było bezpieczne.
        
        # Jeśli zdefiniowano listę startową w zakładce 'Zawodnicy' – użyj jej (z zachowaniem kolejności)
        try:
            if hasattr(self, "selected_df") and isinstance(self.selected_df, pd.DataFrame) and not self.selected_df.empty:
                sel = self.selected_df.copy()
                key_cols = [c for c in ["Zawodnik", "Kraj"] if c in roster.columns and c in sel.columns]
                if not key_cols and "Zawodnik" in roster.columns and "Zawodnik" in sel.columns:
                    key_cols = ["Zawodnik"]
                if key_cols:
                    # połącz wg kluczy, zachowując kolejność 'Nr' (jeśli jest)
                    if "Nr" in sel.columns:
                        sel_keys = sel[key_cols + ["Nr"]].copy()
                        roster = sel_keys.merge(roster, on=key_cols, how="left").sort_values("Nr", kind="mergesort").reset_index(drop=True)
                    else:
                        sel_keys = sel[key_cols].drop_duplicates()
                        roster = sel_keys.merge(roster, on=key_cols, how="left").reset_index(drop=True)


                    # W trybach klasyczny/KO50 – żadnych BYE w rosterze.
                    # KO64 i tak dopełnia BYE wewnątrz swojej drabinki.
                    try:
                        if not self.var_ko64_full.get():
                            mask_bye = (
                                (("Kraj" in roster.columns) and roster["Kraj"].astype(str).str.upper().eq("BYE")) |
                                (("Zawodnik" in roster.columns) and roster["Zawodnik"].astype(str).str.match(BYE_NAME_RE))
                            )
                            if hasattr(mask_bye, "any") and mask_bye.any():
                                roster = roster[~mask_bye].reset_index(drop=True)
                                self.log("ℹ Usunięto ręcznie dodane wiersze BYE z listy startowej (nie są potrzebne).")
                    except Exception as _e:
                        self.log(f"[WARN] Czyszczenie BYE pominięte: {_e}")


        except Exception as _e:
            self.log(f"[WARN] Lista startowa pominięta: {_e}")


        rng = np.random.default_rng()
        outdir_path = Path(outdir); outdir_path.mkdir(parents=True, exist_ok=True)

                # === WYBÓR TRYBU → NAJPIERW SYMULACJA, POTEM RYSOWANIE ===

        # === 1) SYMULACJA ===
        extra = {}
        
        if self.var_ko64_full.get():
            # KO64 – uruchom pełną symulację (zbuduje 'extra' z arkuszami „KO64 - Drabinka” i „KO64 - Klasyfikacja”)
            kwal_df, kval_rank, contest_rows, klasyf, extra_ret = simulate_full_ko64_tournament(
                roster=roster,
                K=k, HS=hs, meter_value=(meter if meter is not None else sim.compute_meter_value(k)),
                wind_ms_mean=wind_mean, wind_ms_sd=wind_sd,
                gate_base=gate, gate_points_per_step=4.0,
                p_gate_change=p_gate, max_gate_delta=max_gate,
                rng=rng, randomness=randomness, elite_regress=elite_regress,
                wind_phi=wind_phi, wind_takeoff_gain=takeoff_gain,
                wind_flight_gain=flight_gain, judges_rho=judges_rho
            )
            # Zachowaj dodatkowe arkusze (drabinka/klasyfikacja) do późniejszego rysowania zakładek
            extra = extra_ret or {}

        elif self.var_ko50.get():
        
            # KO50 (Turniej 4 Skoczni style – pary + Lucky Losers)
            kwal_df, kval_rank, contest_rows, klasyf, extra_ret = sim.simulate_ko_competition(
                roster=roster, K=k, HS=hs, meter_value=(meter if meter is not None else sim.compute_meter_value(k)),
                qual_spots=int(self.var_qual_spots.get()),
                wind_ms_mean=wind_mean, wind_ms_sd=wind_sd,
                gate_base=gate, gate_points_per_step=4.0,
                p_gate_change=p_gate, max_gate_delta=max_gate,
                rng=rng, randomness=randomness, elite_regress=elite_regress,
                wind_phi=wind_phi, wind_takeoff_gain=takeoff_gain,
                wind_flight_gain=flight_gain, judges_rho=judges_rho
            )
            extra = extra_ret or {}
            ex = extra or {}
            ko_ll = ex.get("KO - Lucky Losers", None)
            if isinstance(ko_ll, pd.DataFrame) and not ko_ll.empty:
                df_ll = ko_ll.copy()
                # Standaryzacje nazw, na wszelki wypadek
                if "Punkty rundy" in df_ll.columns and "Punkty R1" not in df_ll.columns:
                    df_ll.rename(columns={"Punkty rundy":"Punkty R1"}, inplace=True)
                if "Odległość" in df_ll.columns and "Odl.1" not in df_ll.columns:
                    df_ll.rename(columns={"Odległość":"Odl.1"}, inplace=True)
                wanted_ll = ["Miejsce w rundzie","Zawodnik","Kraj","Odl.1","Punkty R1","LL"]
                show_ll = [c for c in wanted_ll if c in df_ll.columns]
                df_ll = df_ll.loc[:, show_ll].copy().fillna("")
                self._reset_and_set_table("ko_ll_tree", getattr(self, "ko_ll_body", self.tab_ko_ll), df_ll)
            else:
                self._reset_and_set_table("ko_ll_tree", getattr(self, "ko_ll_body", self.tab_ko_ll), pd.DataFrame())
        
            # KO64 off w trybie KO50
            t = getattr(self, 'ko64_bracket_tree', None)
            
            # bezpieczne resetowanie tabeli drabinki KO64
            if t is not None:
                t.set_dataframe(pd.DataFrame())
        
        else:
            # Klasyczny IND
            kwal_df, kval_rank, contest_rows, klasyf = sim.simulate_competition(
                roster=roster, round_cuts=[int(x) for x in self.var_round_cuts.get().split(",") if x.strip()],
                K=k, HS=hs, meter_value=(meter if meter is not None else sim.compute_meter_value(k)),
                wind_ms_mean=wind_mean, wind_ms_sd=wind_sd,
                gate_base=gate, gate_points_per_step=4.0,
                p_gate_change=p_gate, max_gate_delta=max_gate,
                rng=rng, randomness=randomness, elite_regress=elite_regress,
                wind_phi=wind_phi, wind_takeoff_gain=takeoff_gain,
                wind_flight_gain=flight_gain, judges_rho=judges_rho,
                qual_spots=int(self.var_qual_spots.get())
            )
            extra = {}

        ex = extra or {}  # bezpieczny alias

        # === WCZESNY ZAPIS DO EXCELA (przed rysowaniem UI) ===
        def _falls_from(df, etap):
            if not isinstance(df, pd.DataFrame) or df.empty or "Upadek" not in df.columns:
                return None
            # ZMIANA: obsługuje bool, 0/1, "PRAWDA"/"FAŁSZ", "TRUE"/"FALSE"
            m = df["Upadek"].apply(_to_bool)
            if not m.any():
                return None
            cols = [c for c in ["Runda","Zawodnik","Kraj","Odległość"] if c in df.columns]
            out = df.loc[m, cols].copy()
            if "Runda" in out.columns:
                s = pd.to_numeric(out["Runda"], errors="coerce")
                out["Runda"] = s.map(lambda v: "Q" if pd.isna(v) else str(int(v)))
                out["Runda"] = out["Runda"].astype(object)
            return out

        _frames = []
        for _f in (_falls_from(contest_rows, "Konkurs"), _falls_from(kwal_df, "Kwalifikacje")):
            if isinstance(_f, pd.DataFrame):
                _frames.append(_f)
        falls_df = pd.concat(_frames, ignore_index=True) if _frames else pd.DataFrame()
        try:
            falls_df = _enrich_falls_with_meta(falls_df, roster)
        except Exception as e:
            print("DEBUG FALLS enrich error:", e)
        
        # --- Kontuzje po upadkach (naprawione) ---
        try:
            if not falls_df.empty:
                falls_df = _annotate_falls_with_injuries(falls_df, roster, rng)
            ex["Upadki"] = falls_df # upewniamy się, że zaktualizowana wersja trafia do tabeli
        except Exception as _inj_e:
            self.log(f"[WARN] Kontuzje: {_inj_e}")
            ex["Upadki"] = falls_df
        # zapamiętaj ostatnie wyniki Upadków i agregat (do przycisku w GUI)
        try:
            self._falls_last_df = falls_df.copy() if 'falls_df' in locals() and hasattr(falls_df, "copy") else (
                self._falls_last_df if hasattr(self, "_falls_last_df") else None
            )
        except Exception:
            try:
                self._falls_last_df = falls_df.copy()
            except Exception:
                pass
        try:
            self._falls_last_agg = _agg.copy() if '_agg' in locals() and hasattr(_agg, "copy") else (
                self._falls_last_agg if hasattr(self, "_falls_last_agg") else None
            )
        except Exception:
            pass
        # Agregat: max dni/penalty per zawodnik (przydatne do aktualizacji bazy)
        try:
            _agg_cols = [c for c in ["Zawodnik","Kraj","Kontuzja (dni)","Długość kontuzji (WEEK)","ΔUM (kontuzja)","ΔForma (kontuzja)"] if c in falls_df.columns]
            if len(_agg_cols) >= 3:
                _ff = falls_df[_agg_cols].copy()
                # we aggregate by max days and take corresponding max absolute penalty
                _agg = _ff.groupby(["Zawodnik","Kraj"], as_index=False).agg({
                    "Kontuzja (dni)": "max",
                    "ΔUM (kontuzja)": "min",       # penalties are negative
                    "ΔForma (kontuzja)": "min"
                })
                ex["Kontuzje - Agregat"] = _agg
        except Exception as _agg_e:
            self.log(f"[WARN] Agregat kontuzji: {_agg_e}")
    
    

        # Zapisz Excela już teraz żeby mieć plik nawet jeśli rysowanie UI się wywali
        outpath = sim.save_to_excel(
            roster, kwal_df, kval_rank, contest_rows, klasyf,
            outdir_path, hill, extra_sheets=ex
        )
        self.log(f"✔ {hill} – {len(roster)} zawodników")

        # === 2) ZAKŁADKI KO ===
        if self.var_ko64_full.get():
            # KO64 – tabela + grafika
            # KO64 – tabela + grafika (bez fallbacków – używamy tylko extra["KO64 - Drabinka"])
            df_br_raw = ex.get("KO64 - Drabinka", pd.DataFrame())
            def _hi(row):
                    zw = str(row.get("Zwycięzca", "")).strip()
                    za = str(row.get("Zawodnik A", "")).strip()
                    zb = str(row.get("Zawodnik B", "")).strip()
                    return None
            self._reset_and_set_table("ko64_bracket_tree", getattr(self, "ko64_bracket_table_body", self.tab_ko64_bracket_tbl), df_br_raw, highlighter=_hi)
            try:
                if hasattr(self, "ko64_bracket"):
                    self.ko64_bracket.draw_bracket(df_br_raw)
            except Exception as _e:
                print("[KO64 bracket] draw error:", _e)

            if isinstance(df_br_raw, pd.DataFrame) and not df_br_raw.empty:
                if "Zawodnik" in df_br_raw.columns and "Zawodnik A" not in df_br_raw.columns:
                    # per-row już gotowe -> dokładamy separatory
                    rows = []
                    last_round = None
                    for _, r in df_br_raw.iterrows():
                        rd = r.get("Runda", "")
                        if rd != last_round:
                            rows.append({"Runda": f"— {rd} —", "Para":"", "Seed":"", "Zawodnik":"", "Kraj":"", "Odl.":"", "Punkty":"", "Wygrana":""})
                            last_round = rd
                        rows.append(r.to_dict())
                    df_br = pd.DataFrame(rows)
                else:
                    # wide -> konwersja do per-row + separatory
                    rows = []
                    last_round = None
                    for _, r in df_br_raw.iterrows():
                        rd = r.get("Runda", "")
                        if rd != last_round:
                            rows.append({"Runda": f"— {rd} —", "Para":"", "Seed":"", "Zawodnik":"", "Kraj":"", "Odl.":"", "Punkty":"", "Wygrana":""})
                            last_round = rd
                        winner_name = str(r.get("Zwycięzca", "")).strip()
                        for side in ("A","B"):
                            rows.append({
                                "Runda": rd, "Para": r.get("Para",""),
                                "Seed": r.get(f"Seed {side}", ""), "Zawodnik": r.get(f"Zawodnik {side}", ""), "Kraj": r.get(f"Kraj {side}", ""),
                                "Odl.": r.get(f"Odl {side} (m)", r.get(f"Odległość {side}", r.get(f"Odl.{side}", ""))),
                                "Punkty": r.get(f"Punkty {side}", ""), "Wygrana": "✓" if str(r.get(f"Zawodnik {side}", "")) == winner_name and winner_name else "✗"
                            })
                    df_br = pd.DataFrame(rows)
                wanted = ["Runda","Para","Seed","Zawodnik","Kraj","Odl.","Punkty","Wygrana"]
                df_br = df_br.loc[:, [c for c in wanted if c in df_br.columns]]
            else:
                df_br = pd.DataFrame()

            def _hi_br(row):
                if str(row.get("Zawodnik","")).strip()=="" and str(row.get("Para","")).strip()=="" and str(row.get("Seed","")).strip()=="":
                    lbl = str(row.get("Runda",""))
                    if lbl.startswith("—") and lbl.endswith("—"):
                        return "sep"
                return "ok" if str(row.get("Wygrana","")) in ("✓","True","1") else None

            self._reset_and_set_table(
                "ko64_bracket_tree",
                getattr(self, "ko64_bracket_table_body", self.tab_ko64_bracket_tbl),
                df_br,
                highlighter=_hi_br
            )
            self.ko50_tree.set_dataframe(pd.DataFrame())
            self.ko_ll_tree.set_dataframe(pd.DataFrame())
        elif self.var_ko50.get():
            ex = extra or {}
            ko_pairs = ex.get("KO - Pary (R1)", None)
            if not isinstance(ko_pairs, pd.DataFrame):
                ko_pairs = ex.get("KO - Pary", None)
            ko_ll = ex.get("KO - Lucky Losers", None)

            # --- KO50 – PARY: dokładne kolumny + zielono/bold zwycięzcy i LL ---
            if isinstance(ko_pairs, pd.DataFrame) and not ko_pairs.empty:
                df_pairs = ko_pairs.copy()
        
                # Ujednolicenie nazwy odległości
                if "Odległość" not in df_pairs.columns and "Odległość (m)" in df_pairs.columns:
                    df_pairs.rename(columns={"Odległość (m)":"Odległość"}, inplace=True)
        
                wanted_pairs = ["Para","Zawodnik","Kraj","Odległość","Punkty rundy","Status"]
                show_pairs = [c for c in wanted_pairs if c in df_pairs.columns]
                df_pairs = df_pairs.loc[:, show_pairs].copy().fillna("")
        
                # Highlighter: zielone tło + bold dla "Z pary" i "Lucky Loser"
                def _hi_pairs(row):
                    st = str(row.get("Status","")).strip()
                    return "ok" if st in ("Z pary","Lucky Loser") else None
        
                self._reset_and_set_table("ko50_tree", getattr(self, "ko50_body", self.tab_ko50_pairs), df_pairs, highlighter=_hi_pairs)
            else:
                self._reset_and_set_table("ko50_tree", getattr(self, "ko50_body", self.tab_ko50_pairs), pd.DataFrame())
        
            # --- KO – LUCKY LOSERS: dokładne kolumny ---
            if isinstance(ko_ll, pd.DataFrame) and not ko_ll.empty:
                df_ll = ko_ll.copy()
                if "Punkty rundy" in df_ll.columns and "Punkty R1" not in df_ll.columns:
                    df_ll.rename(columns={"Punkty rundy":"Punkty R1"}, inplace=True)
                if "Odległość" in df_ll.columns and "Odl.1" not in df_ll.columns:
                    df_ll.rename(columns={"Odległość":"Odl.1"}, inplace=True)
                wanted_ll = ["Miejsce w rundzie","Zawodnik","Kraj","Odl.1","Punkty R1","LL"]
                show_ll = [c for c in wanted_ll if c in df_ll.columns]
                df_ll = df_ll.loc[:, show_ll].copy().fillna("")
                self._reset_and_set_table("ko_ll_tree", getattr(self, "ko_ll_body", self.tab_ko_ll), df_ll)
            else:
                self._reset_and_set_table("ko_ll_tree", getattr(self, "ko_ll_body", self.tab_ko_ll), pd.DataFrame())
        
            # KO64 drabinka OFF w trybie KO50
            t = getattr(self, 'ko64_bracket_tree', None)
            
            # bezpieczne resetowanie tabeli drabinki KO64
            if t is not None:
                t.set_dataframe(pd.DataFrame())

        else:
            # klasyczny – wyczyść karty KO
            self.ko50_tree.set_dataframe(pd.DataFrame())
            self.ko_ll_tree.set_dataframe(pd.DataFrame())
            t = getattr(self, 'ko64_bracket_tree', None)
            
            # bezpieczne resetowanie tabeli drabinki KO64
            if t is not None:
                t.set_dataframe(pd.DataFrame())

        # === 3) PODGLĄD WYNIKÓW (kwal + klasyfikacja) – bez 'nan' ===
        # kwal
        kval_show = kval_rank.copy()
        if not kval_show.empty and "Punkty" in kval_show.columns:
            kval_show["Punkty"] = pd.to_numeric(kval_show["Punkty"], errors="coerce").round(1)
        cols = ["Seed","Miejsce","Zawodnik","Kraj","Punkty"]
        kval_to_show = kval_show.copy()
        if all(c in kval_show.columns for c in cols):
            kval_to_show = kval_show[[c for c in cols if c in kval_show.columns]]
        if isinstance(kval_to_show, pd.DataFrame) and "Punkty" in kval_to_show.columns:
            dist_cols = [c for c in kval_show.columns if isinstance(c,str) and (c.startswith("Odl") or "Odleg" in c)]
            base = [c for c in ["Seed","Miejsce","Zawodnik","Kraj"] if c in kval_to_show.columns]
            order = base + [c for c in dist_cols if c in kval_to_show.columns] + ["Punkty"]
            kval_to_show = kval_to_show[[c for c in order if c in kval_to_show.columns]]
        kval_to_show = _normalize_points(kval_to_show, col="Punkty", decimals=1)
        kval_to_show = self._limit_df(kval_to_show, self.var_prev_qual_all.get(), self.var_prev_qual_n.get()).fillna("")
        # zapamiętaj klasyfikację kwalifikacji do aktualizacji Q1/Q2 w turniejach
        try:
            self._last_qual_cls = kval_rank.copy()
        except Exception:
            self._last_qual_cls = None
        self.qual_tree.set_dataframe(kval_to_show)


        # klasyfikacja końcowa
        final_df = klasyf.copy()
        if isinstance(final_df, pd.DataFrame) and "Miejsce" in final_df.columns:
            try:
                final_df["Punkty FIS"] = _fis_points_for_place(final_df["Miejsce"])
            except Exception:
                # awaryjnie, gdyby import się nie udał
                final_df["Punkty FIS"] = 0
        if not final_df.empty:
            dist_cols = [c for c in final_df.columns if isinstance(c,str) and (c.startswith("Odl") or "Odleg" in c)]
            base = [c for c in ["Miejsce","Zawodnik","Kraj","Seed"] if c in final_df.columns]
            cols_order = base + dist_cols + (["Punkty"] if "Punkty" in final_df.columns else []) + (["Punkty FIS"] if "Punkty FIS" in final_df.columns else [])
            final_df = final_df[[c for c in cols_order if c in final_df.columns]]
        # --- [NOWE] zapamiętaj klasyfikację końcową do późniejszej aktualizacji plików
        try:
            self._last_final_cls = klasyf.copy()
        except Exception:
            self._last_final_cls = None

        # Dla KO64: podgląd wyników pokazuje KO64-Klasyfikację zamiast klasyf
        df_ko64_preview = ex.get("KO64 - Klasyfikacja", None)
        if isinstance(df_ko64_preview, pd.DataFrame) and not df_ko64_preview.empty:
            # Dodaj Punkty FIS do KO64 jeśli ich nie ma
            try:
                ko64_display = df_ko64_preview.copy()
                if "Miejsce" in ko64_display.columns and "Punkty FIS" not in ko64_display.columns:
                    ko64_display["Punkty FIS"] = _fis_points_for_place(ko64_display["Miejsce"])
            except Exception:
                ko64_display = df_ko64_preview.copy()
            ko64_display = _normalize_points(ko64_display, col="Punkty", decimals=1)
            ko64_display = self._limit_df(ko64_display, self.var_prev_final_all.get(), self.var_prev_final_n.get()).fillna("")
            self.final_tree.set_dataframe(ko64_display)
        else:
            final_df = _normalize_points(final_df, col="Punkty", decimals=1)
            final_df = self._limit_df(final_df, self.var_prev_final_all.get(), self.var_prev_final_n.get()).fillna("")
            self.final_tree.set_dataframe(final_df)
        # === 4) KO64 – Klasyfikacja (nowa zakładka) – bez 'nan' ===
        df_ko64_klasyf = ex.get("KO64 - Klasyfikacja", pd.DataFrame())
        if isinstance(df_ko64_klasyf, pd.DataFrame) and not df_ko64_klasyf.empty:
            df_ko64_klasyf = df_ko64_klasyf.fillna("")
        if hasattr(self, "ko64_klasyf_tree"):
            df_ko64_klasyf = _normalize_points(df_ko64_klasyf, col="Punkty", decimals=1)
            self._last_ko64_cls = df_ko64_klasyf.copy() 
            self.ko64_klasyf_tree.set_dataframe(df_ko64_klasyf)

        
        # === FALLS (tylko GUI – Excel zapisany wyżej) ===
        try:
            falls_df = ex.get("Upadki", pd.DataFrame())
            self.falls_tree.set_dataframe(_prepare_falls_df_for_gui(falls_df))
        except Exception:
            pass

        # === synchronizacja cyklu Podglądu z aktualnym cyklem w Parametrach ===
        try:
            _sync_cycles = {"GP","SCOC","WC","COC","FC","JC","MC","PC","QC","TC","AC","BC","DC"}
            _cur_cycle = self.var_cycle.get().strip()   # np. "WC-M", "FC-W"
            import re as _re2
            _m = _re2.match(r"^([A-Z]+)-([MW])$", _cur_cycle)
            if _m and _m.group(1) in _sync_cycles:
                _cls_vals = list(self._cls_cycle_cb["values"])
                if _cur_cycle in _cls_vals:
                    self._cls_cycle_var.set(_cur_cycle)
        except Exception:
            pass

class Labeled(ttk.Frame):
    def __init__(self, parent, title):
        super().__init__(parent)
        ttk.Label(self, text=title, font=(None, 10, "bold")).pack(anchor="w")
        self.body = ttk.Frame(self); self.body.pack(fill=tk.BOTH, expand=True, pady=(4,0))

def file_row(parent, label, var, cb, is_dir=False):
    row = ttk.Frame(parent); row.pack(fill=tk.X, pady=2)
    ttk.Label(row, text=label, width=28, anchor="w").pack(side=tk.LEFT)
    ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Button(row, text=("Wybierz folder" if is_dir else "Wybierz plik"), command=cb).pack(side=tk.LEFT, padx=4)

def grid_entries(parent, items):
    for i, (label, var, _cast) in enumerate(items):
        ttk.Label(parent, text=label).grid(row=i, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var, width=20).grid(row=i, column=1, sticky="w", pady=2)

class FrozenFirstColTable(ttk.Frame):
    """Tabela z zamrożoną 1. kolumną (np. 'Miejsce') i flagą przy Zawodniku w części głównej."""
    def __init__(self, parent, frozen_col="Miejsce"):
        super().__init__(parent)
        self.frozen_col = frozen_col
        self._flags = None
        self._flag_col = "Kraj"
        self._name_col = "Zawodnik"

        # --- LEWA część w wąskiej ramce (żeby nie rosła) ---
        self.fixed_wrap = ttk.Frame(self)                 # << nowa, „sztywna” ramka
        self.fixed_wrap.grid(row=0, column=0, sticky="ns")
        self.fixed_wrap.rowconfigure(0, weight=1)
        self.fixed_wrap.columnconfigure(0, weight=1)

        self.tv_fixed = ttk.Treeview(self.fixed_wrap, columns=(self.frozen_col,), show="headings")
        self.tv_main  = ttk.Treeview(self, columns=(), show="tree headings")
        
        self._sel_sync_lock = False  # <— flaga anty-ping-pong

        self.tv_fixed.bind("<<TreeviewSelect>>", self._on_fixed_select)
        self.tv_main.bind("<<TreeviewSelect>>", self._on_main_select)

        # wspólny pionowy scrollbar + poziomy dla części prawej
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self._yview_both)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tv_main.xview)
        self.tv_fixed.configure(yscrollcommand=self._ysb_from_fixed)
        self.tv_main.configure(yscrollcommand=self._ysb_from_main, xscrollcommand=self.hsb.set)

        # układ
        self.columnconfigure(0, weight=0, minsize=40)     # kolumna z „Nr” nie rozciąga się
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.tv_fixed.grid(row=0, column=0, sticky="nsew", in_=self.fixed_wrap)
        self.tv_main.grid(row=0, column=1, sticky="nsew")
        self.vsb.grid(row=0, column=2, sticky="ns")
        self.hsb.grid(row=1, column=1, sticky="ew")


        # synchronizacja selekcji
        self._sel_sync_lock = False
        self.tv_fixed.bind("<<TreeviewSelect>>", self._sync_from_fixed)
        self.tv_main.bind("<<TreeviewSelect>>", self._sync_from_main)

        # styl separatora (opcjonalnie)
        self.tv_main.tag_configure("sep", background="#ECECEC", font=("TkDefaultFont", 9, "bold"))

    # === SORTOWANIE NAGŁÓWKAMI (klik) — PRAWIDŁOWE, NA POZIOMIE KLASY ===
    def enable_sorting(self, numeric_cols=("UM", "Forma", "Punkty", "Seed")):
        """Włącz sortowanie po kliknięciu w nagłówek.
        numeric_cols – kolumny wymuszane jako liczbowe.
        """
        self._numeric_cols_for_sort = set(str(c) for c in (numeric_cols or ()))
        self._sort_state = {"col": None, "asc": True}
        self._install_set_df_hook()
        # jeśli tabela już narysowana – od razu podłącz nagłówki
        try:
            self._bind_sort_headings()
        except Exception:
            pass

    def _install_set_df_hook(self):
        """Przechwyć set_dataframe, by zapamiętywać DF i zawsze rebindować nagłówki."""
        if getattr(self, "_setdf_wrapped", False):
            return
        self._setdf_wrapped = True
        self._orig_set_dataframe = self.set_dataframe

        def _wrapped_set_dataframe(df):
            try:
                
                self._last_df = df.copy() if isinstance(df, pd.DataFrame) else None
            except Exception:
                self._last_df = df
            res = self._orig_set_dataframe(df)
            try:
                self._bind_sort_headings()
            except Exception:
                pass
            return res

        # nadpisanie metody instancji – ok w Tk
        self.set_dataframe = _wrapped_set_dataframe

    def _bind_sort_headings(self):
        """Podepnij komendy do wszystkich nagłówków."""
        # zamrożona kolumna (np. 'Lp.' / 'Miejsce')
        try:
            self.tv_fixed.heading(self.frozen_col, text=self.frozen_col,
                                  command=lambda c=self.frozen_col: self._on_sort_click(c))
        except Exception:
            pass

        # kolumna #0 (tekst w drzewie) – traktujemy jako 'Zawodnik', jeśli istnieje
        try:
            head0 = self.tv_main.heading("#0")
            txt0 = head0.get("text", "") if isinstance(head0, dict) else ""
            self.tv_main.heading("#0", text=(txt0 or "Zawodnik"),
                                 command=lambda c="Zawodnik": self._on_sort_click(c))
        except Exception:
            pass

        # pozostałe kolumny (po prawej)
        try:
            for c in list(self.tv_main["columns"]):
                self.tv_main.heading(c, text=c, command=lambda col=c: self._on_sort_click(col))
        except Exception:
            pass

    def _on_sort_click(self, col):
        """Sortuj po kolumnie (toggle rosnąco/malejąco)."""
        df = getattr(self, "_last_df", None)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return

        # stan sortowania (toggle)
        self._sort_state = getattr(self, "_sort_state", {})
        asc = True if self._sort_state.get("col") != col else (not self._sort_state.get("asc", True))

        # dopasuj nazwę kolumny do realnej kolumny DF (case-insensitive)
        col_in_df = str(col)
        if col_in_df not in df.columns:
            low = str(col_in_df).strip().lower()
            for c in df.columns:
                if str(c).strip().lower() == low:
                    col_in_df = c
                    break
            else:
                return  # brak takiej kolumny w DF

        # helper: bazowy tag zawodów (obcinamy -M / -W)
        try:
            _base_tag = _comp_base_tag  # jeśli wcześniej zdefiniowany globalnie
        except NameError:
            def _base_tag(val: str) -> str:
                s = str(val or "").strip().upper()
                return re.sub(r"-(?:M|W)$", "", s)

        # --- specjalny porządek dla kolumny 'Zawody' (senior + junior) ---
        if str(col_in_df).strip().lower() == "zawody":
            order = {
                # SENIOR
                "WC": 0, "COC": 1, "FC": 2, "GP": 3, "SCOC": 4,
                # JUN
                "JC":10, "MC":11, "PC":12, "QC":13, "TC":14, "AC":15, "BC":16, "DC":17,
            }
            base = df[col_in_df].map(_base_tag)
            key = base.map(lambda k: order.get(k, 999))
            df_sorted = (
                df.assign(__key=key, __val=df[col_in_df].astype(str).str.upper())
                .sort_values(["__key", "__val"], ascending=[asc, asc], kind="mergesort")
                .drop(columns=["__key", "__val"])
            )
        else:
            # zwykłe sortowanie: spróbuj liczbowo, w przeciwnym razie tekstowo (case-insensitive)
            s = df[col_in_df]
            s_num = pd.to_numeric(s, errors="coerce")
            if s_num.notna().sum() >= max(1, len(s) // 2):
                key = s_num  # głównie numery
            else:
                key = s.astype(str).str.casefold()
            df_sorted = (
                df.assign(__key=key)
                .sort_values("__key", ascending=asc, kind="mergesort")
                .drop(columns="__key")
            )

        # zapamiętaj stan sortu
        self._sort_state = {"col": col, "asc": asc}
        self._last_df = df_sorted

        # odśwież widok
        if hasattr(self, "_set_dataframe_after_sort"):
            try:
                self._set_dataframe_after_sort(df_sorted)
                return
            except Exception:
                pass
        if hasattr(self, "set_dataframe"):
            self.set_dataframe(df_sorted)


    def _on_fixed_select(self, _event=None):
        if self._sel_sync_lock:
            return
        sel = self.tv_fixed.selection()
        if not sel:
            return
        idx = self.tv_fixed.index(sel[0])
        right = self.tv_main.get_children()
        if idx < len(right):
            try:
                self._sel_sync_lock = True
                target = right[idx]
                # ustaw tylko gdy trzeba – to ucina kaskadę zdarzeń
                if target not in self.tv_main.selection():
                    self.tv_main.selection_set(target)
                self.tv_main.see(target)
            finally:
                self._sel_sync_lock = False

    def _on_main_select(self, _event=None):
        if self._sel_sync_lock:
            return
        sel = self.tv_main.selection()
        if not sel:
            return
        idx = self.tv_main.index(sel[0])
        left = self.tv_fixed.get_children()
        if idx < len(left):
            try:
                self._sel_sync_lock = True
                target = left[idx]
                if target not in self.tv_fixed.selection():
                    self.tv_fixed.selection_set(target)
                self.tv_fixed.see(target)
            finally:
                self._sel_sync_lock = False

# konfiguracja flag
    def enable_flags_after_name(self, flag_dir, kraj_col="Kraj", name_col="Zawodnik"):
        self._flags = _FlagCache(flag_dir)
        self._flag_col = kraj_col
        self._name_col = name_col

    # set danych
    def set_dataframe(self, df: pd.DataFrame):
        for tv in (self.tv_fixed, self.tv_main):
            for iid in tv.get_children(): tv.delete(iid)

        if df is None or getattr(df, "empty", True):
            self.tv_fixed["columns"] = (self.frozen_col,)
            self.tv_main["columns"] = []
            return
        
        if self.frozen_col not in df.columns:
            df = df.copy()
            df.insert(0, self.frozen_col, range(1, len(df) + 1))

        cols = list(df.columns)
        fcol = self.frozen_col if self.frozen_col in cols else None
        kcol = self._flag_col  if self._flag_col  in cols else None
        ncol = self._name_col  if self._name_col  in cols else None

        # lewa: tylko 'Miejsce'
        if fcol:
            self.tv_fixed["columns"] = (fcol,)
            self.tv_fixed.heading(fcol, text=fcol)
            self.tv_fixed.column(fcol, width=36, minwidth=32, stretch=False, anchor="center")
        else:
            self.tv_fixed["columns"] = ()

        try:
            lock = 36 if str(self.frozen_col).lower() in ("nr", "miejsce") else 56
            self._lock_fixed_width(lock + 10)
        except Exception:
            pass

        # prawa: #0 = Zawodnik; po nim 'Kraj' i reszta
        self.tv_main.heading("#0", text=ncol or "Zawodnik")
        self.tv_main.column("#0", width=220, anchor="w")
        rest = [c for c in cols if c not in (fcol, ncol, kcol)]
        main_cols = ([kcol] if kcol else []) + rest
        self.tv_main["columns"] = main_cols
        for c in main_cols:
            self.tv_main.heading(c, text=c)
            self.tv_main.column(c, width=max(60, int(8 * len(str(c)))), anchor="w")

        # wiersze (ta sama kolejność po obu stronach → łatwa synchronizacja)
        for _, row_s in df.iterrows():
            row = dict(row_s)

            # separator? (gdyby się trafił)
            if kcol:
                code = str(row.get(kcol, "") or "")
                if code.strip().startswith("—") and code.strip().endswith("—"):
                    iid_r = self.tv_main.insert("", "end", text=f" {row.get(ncol,'')}", values=(), tags=("sep",))
                    self.tv_fixed.insert("", "end", values=(row.get(fcol, ""),))
                    continue

            img = _flag_cached(row.get(kcol, "")
) if self._flags and kcol else None
            txt0 = f" {row.get(ncol,'')}"
            # helper: czy to realny obiekt Tk PhotoImage?
            def _is_tk_image(x):
                try:
                    return str(x).startswith("pyimage")
                except Exception:
                    return False

            img = _flag_cached(row.get(kcol, "")
) if self._flags and kcol else None
            safe_img = (img or "")   # jeżeli to nie PhotoImage → bez obrazka
            txt0 = f" {row.get(ncol,'')}"
            iid_r = self.tv_main.insert(
                "", "end",
                text=txt0,
                image=safe_img,
                values=[row.get(c, "") for c in main_cols]
            )
            # wstaw po lewej w tym samym indeksie
            self.tv_fixed.insert("", "end", values=(row.get(fcol, ""),))

    # ---- synchronizacja przewijania i selekcji ----
    def _yview_both(self, *args):
        self.tv_fixed.yview(*args); self.tv_main.yview(*args)
    def _ysb_from_fixed(self, *args):
        self.vsb.set(*args);  self.tv_main.yview_moveto(args[0])
    def _ysb_from_main(self, *args):
        self.vsb.set(*args);  self.tv_fixed.yview_moveto(args[0])
    def _sync_from_fixed(self, _):
        if self._sel_sync_lock:
            return
        sel = self.tv_fixed.selection()
        if not sel:
            return
        idx = self.tv_fixed.index(sel[0])
        right_children = self.tv_main.get_children()
        if idx < len(right_children):
            try:
                self._sel_sync_lock = True
                target = right_children[idx]
                if target not in self.tv_main.selection():
                    self.tv_main.selection_set(target)
                self.tv_main.see(target)
            finally:
                self._sel_sync_lock = False

    def _sync_from_main(self, _):
        if self._sel_sync_lock:
            return
        sel = self.tv_main.selection()
        if not sel:
            return
        idx = self.tv_main.index(sel[0])
        left_children = self.tv_fixed.get_children()
        if idx < len(left_children):
            try:
                self._sel_sync_lock = True
                target = left_children[idx]
                if target not in self.tv_fixed.selection():
                    self.tv_fixed.selection_set(target)
                self.tv_fixed.see(target)
            finally:
                self._sel_sync_lock = False

    def _lock_fixed_width(self, px: int):
        """Zablokuj docelową szerokość lewej części (zamrożona kolumna)."""
        try:
            self.fixed_wrap.configure(width=int(px))
            self.fixed_wrap.grid_propagate(False)  # dziecko nie rozszerzy ramki
        except Exception:
            pass

class Table(ttk.Frame):
    def __init__(self, parent):
        self._mode_flag_after_name = False
        self._name_col = "Zawodnik"
        super().__init__(parent)
        # ← ZMIANA: pozwól na kolumnę tree (#0), gdzie damy flagę+kod
        self.tree = ttk.Treeview(self, columns=(), show="tree headings")
        self.tree.tag_configure(
            "sep",
            background="#ECECEC",            # szare tło
            font=("TkDefaultFont", 9, "bold")  # pogrubienie
        )
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns"); hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1); self.grid_columnconfigure(0, weight=1)

        # highlight tagi (bez zmian) …
        self.highlighter = None
        # …
        # NOWE: konfiguracja flag
        self._flags: _FlagCache | None = None
        self._flag_col = "Kraj"

    # --- EDYCJA KOMÓREK (opcjonalnie włączana) -------------------------------
    def enable_editing(self, editable_cols=("WC", "COC", "FC"), on_commit=None, integer_only=True):
        """
        Włącz edycję podwójnym kliknięciem w podanych kolumnach.
        - editable_cols: tuple/list z nazwami kolumn do edycji
        - on_commit: callback bezargumentowy wywoływany po zapisie zmian
        - integer_only: True → tylko liczby całkowite >= 0
        """
        self._editable_cols = set(str(c) for c in (editable_cols or []))
        self._edit_integer_only = bool(integer_only)
        self._on_edit_commit = on_commit
        # edytor (Entry/Spinbox) tworzony leniwie
        self._cell_editor = None
        self._cell_editor_info = None
        # podwójny klik – start edycji
        try:
            self.tree.bind("<Double-1>", self._begin_cell_edit)
        except Exception:
            pass

        # === SORTOWANIE NAGŁÓWKAMI – dla Table (pojedynczy Treeview) ===
    def enable_sorting(self, numeric_cols=("WC", "COC", "FC", "UM", "Forma", "Punkty")):
        """Włącz sortowanie po kliknięciu w nagłówek."""
        self._numeric_cols_for_sort = set(str(c) for c in (numeric_cols or ()))
        self._sort_state = {"col": None, "asc": True}
        self._install_set_df_hook_table()
        # jeśli tabela już istnieje — od razu podepnij
        try:
            self._bind_sort_headings_table()
        except Exception:
            pass

    def _install_set_df_hook_table(self):
        if getattr(self, "_setdf_wrapped_table", False):
            return
        self._setdf_wrapped_table = True
        self._orig_set_dataframe_table = self.set_dataframe

        def _wrapped(df):
            try:
                
                self._last_df = df.copy() if isinstance(df, pd.DataFrame) else None
            except Exception:
                self._last_df = df
            res = self._orig_set_dataframe_table(df)
            try:
                self._bind_sort_headings_table()
            except Exception:
                pass
            return res

        self.set_dataframe = _wrapped

    def _bind_sort_headings_table(self):
        """Podepnij komendy do wszystkich nagłówków Table."""
        # kolumna #0 – nagłówek to zwykle 'Kraj' lub 'Zawodnik'
        try:
            head0 = self.tree.heading("#0")
            txt0 = head0.get("text", "") if isinstance(head0, dict) else ""
            lab0 = txt0 or "Zawodnik"
            self.tree.heading("#0", text=lab0,
                              command=lambda c=lab0: self._on_sort_click_table(c))
        except Exception:
            pass

        # pozostałe kolumny
        try:
            for c in list(self.tree["columns"]):
                self.tree.heading(c, text=c, command=lambda col=c: self._on_sort_click_table(col))
        except Exception:
            pass

    def _on_sort_click_table(self, col):
        """Sortuj DF po kolumnie; toggle rosnąco/malejąco."""
        
        df = getattr(self, "_last_df", None)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return

        # Mapowanie: gdy kliknięto nagłówek #0 (np. 'Kraj'), ta kolumna może być
        # schowana w danych (bo trafiła do text/#0). Wtedy używamy self._flag_col
        # lub self._name_col – co jest nagłówkiem #0.
        col_in_df = str(col)
        if col_in_df not in df.columns:
            # jeśli #0 to „Kraj” → użyj kolumny flag/kraju; jeśli „Zawodnik” → nazwy
            if str(col).strip().lower() == str(getattr(self, "_flag_col", "Kraj")).strip().lower():
                col_in_df = getattr(self, "_flag_col", "Kraj")
            elif str(col).strip().lower() == str(getattr(self, "_name_col", "Zawodnik")).strip().lower():
                col_in_df = getattr(self, "_name_col", "Zawodnik")

        # kierunek sortu (toggle)
        if self._sort_state.get("col") == col_in_df:
            asc = not self._sort_state.get("asc", True)
        else:
            asc = True

        if col_in_df in self._numeric_cols_for_sort:
            key = pd.to_numeric(df.get(col_in_df, []), errors="coerce").fillna(-1e18)
            df2 = df.assign(__key__=key).sort_values("__key__", ascending=asc, kind="mergesort").drop(columns="__key__")
        else:
            key = df.get(col_in_df, []).astype(str).str.lower()
            df2 = df.assign(__key__=key).sort_values("__key__", ascending=asc, kind="mergesort").drop(columns="__key__")

        self._sort_state.update(col=col_in_df, asc=asc)
        self.set_dataframe(df2)

    def _identify_col_name(self, col_id: str) -> str:
        # col_id: "#0", "#1", "#2", ...
        if col_id == "#0":
            # kolumna drzewa – u nas to „nazwa” (np. 'Kraj') – nie edytujemy
            return ""
        try:
            idx = int(col_id.replace("#", "")) - 1
            cols = list(self.tree["columns"])
            if 0 <= idx < len(cols):
                # heading text to prawdziwa nazwa kolumny
                return str(self.tree.heading(cols[idx]).get("text", cols[idx]))
        except Exception:
            pass
        return ""

    def _begin_cell_edit(self, event):
        try:
            x, y = event.x, event.y
            region = self.tree.identify_region(x, y)
            if region not in ("cell",):
                return
            item = self.tree.identify_row(y)
            col_id = self.tree.identify_column(x)
            col_name = self._identify_col_name(col_id)
            if not col_name or col_name not in getattr(self, "_editable_cols", set()):
                return

            bbox = self.tree.bbox(item, col_id)
            if not bbox:
                return
            # Aktualna wartość
            cur_val = self.tree.set(item, col_id)

            # Editor = Spinbox (int) lub Entry (float/tekst)
            if getattr(self, "_edit_integer_only", True):
                editor = ttk.Spinbox(self, from_=0, to=999, increment=1, width=max(4, int(bbox[2]/8)))
                try:
                    editor.set(int(str(cur_val) if str(cur_val).strip() else "0"))
                except Exception:
                    editor.set(0)
            else:
                editor = ttk.Entry(self)
                editor.insert(0, str(cur_val))

            # Położenie edytora nad komórką
            x0, y0, w, h = bbox
            # Treeview jest w self; przelicz do układu ramki
            ax = self.tree.winfo_rootx() - self.winfo_rootx()
            ay = self.tree.winfo_rooty() - self.winfo_rooty()
            editor.place(x=x0 + ax, y=y0 + ay, width=w, height=h)
            editor.focus_set()

            # Zapamiętaj kontekst
            self._cell_editor = editor
            self._cell_editor_info = (item, col_id, col_name)

            # Zatwierdzanie
            editor.bind("<Return>", lambda e: self._commit_cell_edit())
            editor.bind("<KP_Enter>", lambda e: self._commit_cell_edit())
            editor.bind("<Escape>", lambda e: self._cancel_cell_edit())
            editor.bind("<FocusOut>", lambda e: self._commit_cell_edit())
        except Exception:
            pass

    def _commit_cell_edit(self):
        if not self._cell_editor or not self._cell_editor_info:
            return
        editor = self._cell_editor
        item, col_id, col_name = self._cell_editor_info
        try:
            new_val = editor.get()
            if getattr(self, "_edit_integer_only", True):
                try:
                    v = int(str(new_val).strip() or "0")
                    if v < 0: v = 0
                except Exception:
                    v = 0
                self.tree.set(item, col_id, str(v))
            else:
                self.tree.set(item, col_id, str(new_val))
        finally:
            try:
                editor.destroy()
            except Exception:
                pass
            self._cell_editor = None
            self._cell_editor_info = None

        # callback po zapisie (odświeżenie prawej tabeli)
        cb = getattr(self, "_on_edit_commit", None)
        if callable(cb):
            try:
                cb()
            except Exception:
                pass

    def _cancel_cell_edit(self):
        if not self._cell_editor:
            return
        try:
            self._cell_editor.destroy()
        except Exception:
            pass
        self._cell_editor = None
        self._cell_editor_info = None

    def get_dataframe(self):
        """
        Buduje DataFrame z aktualnej zawartości Treeview.
        Dla tabel WYBÓR zwraca kolumny: Kraj, WC, COC, FC
        (inne kolumny też zostaną zebrane, jeśli istnieją).
        """
        
        cols_ids = list(self.tree["columns"])
        # mapuj id → nagłówek (u nas nagłówki = nazwy kolumn)
        headers = []
        for cid in cols_ids:
            h = self.tree.heading(cid).get("text", cid)
            headers.append(h if h else cid)

        rows = []
        for iid in self.tree.get_children(""):
            item = self.tree.item(iid)
            # tekst w #0 (u nas: nazwa, np. Kraj)
            name_text = str(item.get("text", "")).strip()
            values = list(self.tree.item(iid, "values"))
            row = {}
            # Wstaw #0 jako „Kraj”, jeśli taka kolumna istnieje w danych
            if "Kraj" in headers or True:
                row["Kraj"] = name_text
            for idx, cid in enumerate(cols_ids):
                key = headers[idx]
                row[key] = values[idx] if idx < len(values) else ""
            rows.append(row)

        df = pd.DataFrame(rows)
        # Normalizacja typów dla WC/COC/FC
        for c in ("WC", "COC", "FC"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        if "Kraj" in df.columns:
            df["Kraj"] = df["Kraj"].astype(str).str.upper().str.strip()
        return df

    def enable_flags_after_name(self, flag_dir, kraj_col: str = "Kraj", name_col: str = "Zawodnik"):
        """Tryb: w #0 rysujemy Zawodnika + flagę kraju; kolumna 'Kraj' (kod) idzie tuż za #0."""
        self._flags = _FlagCache(flag_dir)
        self._flag_col = kraj_col
        self._name_col = name_col
        self._mode_flag_after_name = True

        # Włącz #0 i ustaw jako "Zawodnik"
        self.tree.configure(show="tree headings")
        self.tree.heading("#0", text=self._name_col)
        # szerokość nazwiska — dopasuj pod swoje dane
        self.tree.column("#0", width=220, minwidth=160, anchor="w")


    def enable_flags(self, flag_dir, flag_col: str = "Kraj"):
        # cache obrazków
        self._flags = _FlagCache(flag_dir)
        self._flag_col = flag_col

        # KLUCZOWE: włącz widok kolumny #0 (tree), bo tylko tam można rysować obrazek
        # jeśli wcześniej Treeview powstał z show="headings", to to go przełączy
        self.tree.configure(show="tree headings")

        # nagłówek i rozsądna szerokość dla #0
        self.tree.heading("#0", text=self._flag_col)
        self.tree.column("#0", width=100, minwidth=80, stretch=False, anchor="w")

    def set_highlighter(self, fn):
        self.highlighter = fn

    def disable_flags(self):
        self._flags = None
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=20, anchor="w")

    def set_dataframe(self, df):
        # wyczyść
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        if df is None or getattr(df, "empty", True):
            self.tree["columns"] = []
            return

        def _find_col(_df, name: str):
            tgt = str(name).strip().lower()
            for c in _df.columns:
                if str(c).strip().lower() == tgt:
                    return str(c)
            return None

        kcol = _find_col(df, getattr(self, "_flag_col", "Kraj"))
        ncol = _find_col(df, getattr(self, "_name_col", "Zawodnik"))
        use_flags = self._flags is not None and (kcol is not None)

        # --- TRYB: flaga przy nazwisku w #0 (enable_flags_after_name) ---
        if use_flags and self._mode_flag_after_name and (ncol is not None):
            self.tree.configure(show="tree headings")
            self.tree.heading("#0", text=ncol)
            self.tree.column("#0", width=max(180, int(10 * len(ncol))), anchor="w")

            rest = [c for c in df.columns if c not in (ncol, kcol)]
            cols = [kcol] + rest
            self.tree["columns"] = cols
            for c in cols:
                self.tree.heading(c, text=c)
                self.tree.column(c, width=max(60, int(8 * len(str(c)))), anchor="w")

            for _, row_s in df.iterrows():
                row = dict(row_s)
                # tagi
                tags = ()
                if callable(getattr(self, "highlighter", None)):
                    t = self.highlighter(row)
                    if isinstance(t, (list, tuple)): tags = tuple(t)
                    elif t: tags = (t,)

                code = str(row.get(kcol, "") or "")
                if code.strip().startswith("—") and code.strip().endswith("—"):
                    self._safe_tree_insert(text=f" {row.get(ncol,'')}", image=None, values=(), tags=("sep",))
                    continue

                img = _flag_cached(code)
                txt0 = f" {row.get(ncol,'')}"
                values = [row.get(c, "") for c in cols]
                self._safe_tree_insert(text=txt0, image=img, values=values, tags=tags)
            return

        # --- TRYB: flaga w #0 jako 'Kraj' (klasyczny enable_flags) ---
        if use_flags:
            self.tree.configure(show="tree headings")
            self.tree.heading("#0", text=kcol)
            self.tree.column("#0", width=100, minwidth=80, stretch=False, anchor="w")

            cols = [c for c in df.columns if str(c) != kcol]
            self.tree["columns"] = cols
            for c in cols:
                self.tree.heading(c, text=c)
                self.tree.column(c, width=max(60, int(8 * len(str(c)))), anchor="w")

            for _, row_s in df.iterrows():
                row = dict(row_s)
                tags = ()
                if callable(getattr(self, "highlighter", None)):
                    t = self.highlighter(row)
                    if isinstance(t, (list, tuple)): tags = tuple(t)
                    elif t: tags = (t,)

                code = str(row.get(kcol, "") or "")
                if code.strip().startswith("—") and code.strip().endswith("—"):
                    self._safe_tree_insert(text=f" {code}", image=None, values=(), tags=("sep",))
                    continue

                img = _flag_cached(code)
                txt0 = f" {code}"
                values = [row.get(c, "") for c in cols]
                self._safe_tree_insert(text=txt0, image=img, values=values, tags=tags)
            return

        # --- Fallback: bez flag ---
        cols = list(df.columns)
        self.tree.configure(show="headings")
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=max(60, int(8 * len(str(c)))), anchor="w")
        for _, row_s in df.iterrows():
            row = dict(row_s)
            tags = ()
            if callable(getattr(self, "highlighter", None)):
                t = self.highlighter(row)
                if isinstance(t, (list, tuple)): tags = tuple(t)
                elif t: tags = (t,)
            values = [row.get(c, "") for c in cols]
            self._safe_tree_insert(text=None, image=None, values=values, tags=tags)

    def _safe_tree_insert(self, text=None, image=None, values=None, tags=None):
        # zbuduj zawsze poprawny zestaw opcji dla Tk
        opts = {}
        if text is not None:
            opts["text"] = str(text)

        # image tylko gdy faktycznie jest PhotoImage
        if image is not None:
            try:
                _ = image.__str__  # minimalna weryfikacja – PhotoImage ma handler w Tk
                opts["image"] = image
            except Exception:
                pass

        # values -> krotka stringów, bez None/NaN
        seq = []
        if values:
            for v in values:
                if v is None:
                    seq.append("")
                else:
                    try:
                        # np.nan itp.
                        if hasattr(v, "__float__") and str(float(v)) == "nan":
                            seq.append("")
                        else:
                            seq.append(str(v))
                    except Exception:
                        seq.append(str(v))
        if seq:
            opts["values"] = tuple(seq)

        # tags -> krotka stringów
        if tags:
            if isinstance(tags, (list, tuple, set)):
                opts["tags"] = tuple(str(t) for t in tags if t)
            else:
                opts["tags"] = (str(tags),)

        return self.tree.insert("", "end", **opts)

class BracketCanvas(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg="#1e1e1e", highlightthickness=0)
        self.xsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.ysb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.xsb.set, yscrollcommand=self.ysb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.ysb.grid(row=0, column=1, sticky="ns")
        self.xsb.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)

    def clear(self):
        try:
            self.canvas.delete("all")
        except Exception:
            pass

        # --- GEOMETRIA (poprawiona) ---
        self.col_w = 260         # szerokość kafla zawodnika
        self.col_gap = 120       # więcej miejsca na klamry i łączniki
        self.row_h = 24
        self.in_match_gap = 12   # większy odstęp A/B w parze → czytelne R1
        self.margin_x = 28
        self.margin_y = 56

        # bazowy krok pionowy dla R1; kolejne rundy mnożone x2
        self.v_step_base = self.row_h*2 + self.in_match_gap + 18

    # --- NOWE: precyzyjne pozycjonowanie par ---
    def _pair_center(self, r: int, match_no: int) -> float:
        """Y-środek pary (runda r, numer pary zaczyna się od 1)."""
        return self.margin_y + (2**(r-1)) * (match_no - 0.5) * self.v_step_base

    def _pair_y(self, r: int, match_no: int):
        yc = self._pair_center(r, match_no)
        y_top = yc - (self.row_h + self.in_match_gap)/2
        y_bot = yc + (self.row_h + self.in_match_gap)/2
        return y_top, y_bot, yc

    def _round_index(self, label: str) -> int:
        s = str(label).lower()
        # KO64 etapy: R1(64), R2(32), R3(16), QF(8), SF(4), F(2)
        if "runda 1" in s or "r1" in s: return 1
        if "runda 2" in s or "r2" in s: return 2
        if "runda 3" in s or "r3" in s: return 3
        if "qf" in s or "cwierc" in s or "ćwierć" in s: return 4
        if "półfina" in s or "sf" in s: return 5
        if "finał" in s or "final" in s or "f (2)" in s: return 6
        m = re.search(r"r(\d+)", s);  return int(m.group(1)) if m else 1

    def _draw_badge(self, x0, y0, h, text, win=False):
        w = 30
        x1 = x0 + w
        y1 = y0 + h
        color = "#ff6f00" if win else "#616161"
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, width=0)
        self.canvas.create_text((x0+x1)/2, (y0+y1)/2,
                                text=str(text) if text not in (None, "") else "",
                                fill="white", font=("TkDefaultFont", 9, "bold"))

    def _draw_row(self, x, y, width, label_left, score, is_winner):
        fill = "#244f2a" if is_winner else "#2a2a2a"
        outline = "#1f7a28" if is_winner else "#555555"
        self.canvas.create_rectangle(x, y, x+width, y+self.row_h, fill=fill, outline=outline)
        font = ("TkDefaultFont", 9, "bold" if is_winner else "normal")
        self.canvas.create_text(x+8, y+self.row_h/2, text=label_left, anchor="w", fill="#ffffff", font=font)
        self._draw_badge(x+width+8, y, self.row_h,
                         (f"{score:.1f}" if isinstance(score, (int,float)) else score),
                         win=is_winner)

    def draw_bracket(self, df: pd.DataFrame):
        self.clear()
        if not isinstance(df, pd.DataFrame) or df.empty:
            self.canvas.config(scrollregion=(0,0,1000,600))
            self.canvas.create_text(40, 40, text="Brak danych do drabinki KO64", fill="#ddd", anchor="nw")
            return

        df_local = df.copy()
        df_local["__R"] = df_local["Runda"].map(self._round_index)
        rounds = {r: g.sort_values("Para") for r, g in df_local.groupby("__R")}
        Rmax = max(rounds.keys())
        m1 = len(rounds.get(1, pd.DataFrame()))
        total_w = self.margin_x*2 + Rmax*(self.col_w + self.col_gap) + 120
        total_h = self.margin_y*2 + max(1, m1) * self.v_step_base + 200
        self.canvas.config(scrollregion=(0,0,total_w,total_h))

        headers = {1:"Runda 1", 2:"Runda 2", 3:"Runda 3", 4:"Ćwierćfinały", 5:"Półfinały", 6:"Finał"}
        for r in range(1, Rmax+1):
            xhdr = self.margin_x + (r-1)*(self.col_w + self.col_gap)
            self.canvas.create_text(xhdr, 24, text=headers.get(r, f"Runda {r}"),
                                    fill="#ffffff", anchor="w", font=("TkDefaultFont", 10, "bold"))

        for r in range(1, Rmax+1):
            col_x = self.margin_x + (r-1)*(self.col_w + self.col_gap)
            g = rounds.get(r, pd.DataFrame())
            if g.empty: continue

            for _, row in g.iterrows():
                p = int(row.get("Para", 1))
                y_top, y_bot, yc = self._pair_y(r, p)

                nameA = f"{row.get('Kraj A','')}  {row.get('Zawodnik A','')}".strip()
                nameB = f"{row.get('Kraj B','')}  {row.get('Zawodnik B','')}".strip()
                ptsA  = row.get("Punkty A", None)
                ptsB  = row.get("Punkty B", None)
                winner = str(row.get("Zwycięzca","")).strip()
                winA = (str(row.get("Zawodnik A","")).strip() == winner)
                winB = (str(row.get("Zawodnik B","")).strip() == winner)

                # wiersze A/B
                self._draw_row(col_x, y_top, self.col_w, nameA, ptsA, winA)
                self._draw_row(col_x, y_bot, self.col_w, nameB, ptsB, winB)

                # --- NOWE: klamra łącząca parę w tej samej rundzie ---
                right_edge = col_x + self.col_w + 8 + 30  # koniec badge
                join_x = col_x + self.col_w + self.col_gap*0.35
                # krótkie poziome od A i B
                self.canvas.create_line(right_edge, y_top+self.row_h/2, join_x, y_top+self.row_h/2, fill="#9aa1a7", width=2)
                self.canvas.create_line(right_edge, y_bot+self.row_h/2, join_x, y_bot+self.row_h/2, fill="#9aa1a7", width=2)
                # pion łączący i mały „dzióbek” klamry
                self.canvas.create_line(join_x, y_top+self.row_h/2, join_x, y_bot+self.row_h/2, fill="#9aa1a7", width=2)

                # --- przejście zwycięzcy do kolejnej rundy ---
                if r < Rmax:
                    dest_match = (p+1)//2
                    next_col_x = self.margin_x + (r)*(self.col_w + self.col_gap)
                    y_dest_top, y_dest_bot, y_dest_c = self._pair_y(r+1, dest_match)
                    y_dest = y_dest_top if (p % 2 == 1) else y_dest_bot

                    # od klamry do środka kolumny (szara)
                    mid_x = col_x + self.col_w + self.col_gap*0.7
                    self.canvas.create_line(join_x, yc, mid_x, yc, fill="#9aa1a7", width=2)

                    # tylko zwycięzca — wyraźny, pomarańczowy odcinek do slotu następnej rundy
                    self.canvas.create_line(mid_x, yc, next_col_x, y_dest + self.row_h/2, fill="#ff6f00", width=3)

# Standalone
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        try:
            from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
        MainFrame(self)
        # scroll obsługiwany globalnie w głównym oknie (ski_jump_combined_embedded_master_fixed.py)

if __name__ == "__main__":
    App().mainloop()


# ===================== INJURY / MEDICAL MAPS – HELPERS =====================
# These helpers load infrastructure/doctor maps and compute injury outcomes.
# They are placed at the end of the file to avoid interfering with existing imports.

try:
    import numpy as _inj_np
    import pandas as _inj_pd
except Exception:
    _inj_np = None
    _inj_pd = None

_INFRA_MAP = None
_DOCTOR_MAP_M = None
_DOCTOR_MAP_W = None

def _load_infra_map_from_csv(path_candidates=("Infrastruktura S45.csv",)):
    """Return dict NAT->infra(1..5)."""
    global _INFRA_MAP
    if _inj_pd is None:
        return {}
    if _INFRA_MAP:
        return _INFRA_MAP

    # Użyj _find_nearby_file żeby znaleźć plik niezależnie od CWD
    path = _find_nearby_file(
        "Infrastruktura S45.csv",
        alt_patterns=["*Infrastruktura* S45*.csv", "*Infrastruktura*.csv"]
    )
    if not path:
        print("DEBUG _load_infra_map: nie znaleziono pliku")
        return {}

    df = _read_tab_any(path)
    if df is None or df.empty:
        print("DEBUG _load_infra_map: nie udało się wczytać pliku")
        return {}

    # Znajdź kolumny (case-insensitive)
    cols = {str(c).strip(): c for c in df.columns}
    cols_lower = {k.lower(): v for k, v in cols.items()}

    nat_col = next((cols[c] for c in cols if c in ("KRAJ","NAT","Kraj","Country","CODE")), None)
    if not nat_col:
        nat_col = next((cols_lower[k] for k in cols_lower if k in ("kraj","nat","country","code")), None)

    med_col = next((cols[c] for c in cols if c in ("Centrum Medyczne","Infrastruktura","Med","Med_center","MED")), None)
    if not med_col:
        med_col = next((cols_lower[k] for k in cols_lower if "centrum medyczne" in k or "infrastruktura" in k), None)

    if not nat_col or not med_col:
        print(f"DEBUG _load_infra_map: brak kolumn nat={nat_col} med={med_col}, dostępne: {list(df.columns)}")
        return {}

    tmp = df[[nat_col, med_col]].copy()
    tmp[nat_col] = tmp[nat_col].astype(str).str.strip().str.upper()
    tmp[med_col] = _inj_pd.to_numeric(tmp[med_col], errors="coerce").fillna(0).clip(0, 5).astype(int)

    out = dict(zip(tmp[nat_col], tmp[med_col]))
    out = {k: v for k, v in out.items() if k and k != "NAN"}  # usuń puste klucze

    print(f"DEBUG _load_infra_map: załadowano {len(out)} krajów, sample={list(out.items())[:3]}")
    _INFRA_MAP = out
    return _INFRA_MAP

# === POPRAWIONY BLOK MEDYCZNY ===

def _load_doctor_map_from_staff_csv(path_candidates=("Sztab M S45.csv",), sex="M"):
    if _inj_pd is None:
        return {}
    
    # Dynamiczne budowanie nazwy pliku na podstawie płci
    staff_file = f"Sztab {sex} S45.csv"
    # Szukamy pliku w folderze projektu lub folderach nadrzędnych
    path = _find_nearby_file(staff_file, alt_patterns=[f"*Sztab*{sex}*.csv"])
    
    if not path:
        return {}

    try:
        # Używamy Twojej funkcji _read_tab_any (obsługuje separator ';' i kodowanie)
        df = _read_tab_any(path)
        if df is None: return {}

        # Mapowanie kolumn (ignorujemy wielkość liter)
        col_nat = next((c for c in df.columns if str(c).upper() in ["NAT", "KRAJ"]), None)
        col_code = next((c for c in df.columns if str(c).upper() in ["CODE", "KOD"]), None)
        col_um = next((c for c in df.columns if str(c).upper() in ["UM", "UMIEJĘTNOŚCI"]), None)

        if not (col_nat and col_code and col_um):
            return {}

        # Filtrujemy tylko lekarzy (L)
        mask = df[col_code].astype(str).str.strip().str.upper() == "L"
        tmp = df[mask].copy()

        # Konwersja danych
        tmp[col_nat] = tmp[col_nat].astype(str).str.strip().str.upper()
        tmp[col_um] = _inj_pd.to_numeric(tmp[col_um], errors='coerce').fillna(50)

        # Zwracamy słownik {KRAJ: MAX_UM_LEKARZA}
        return tmp.groupby(col_nat)[col_um].max().to_dict()
    except Exception:
        return {}
    
def _ensure_medical_maps_loaded():
    global _INFRA_MAP, _DOCTOR_MAP_M, _DOCTOR_MAP_W
    # ZMIANA: ładuj jeśli None LUB pusty słownik
    if not _INFRA_MAP:
        _INFRA_MAP = _load_infra_map_from_csv()
        print(f"DEBUG _ensure: _INFRA_MAP załadowany, krajów={len(_INFRA_MAP)}")
    _DOCTOR_MAP_M = _load_doctor_map_from_staff_csv(sex="M")
    _DOCTOR_MAP_W = _load_doctor_map_from_staff_csv(sex="W")
    
def _injury_roll__core(infra, doctor, rng):
    """Core injury roll: returns (severity, days)."""
    infra = int(max(1, min(5, int(infra)))) if infra is not None else 3
    doctor = float(max(0.0, min(100.0, float(doctor)))) if doctor is not None else 50.0

    infra_n = (infra - 1) / 4.0
    doc_n   = doctor / 100.0
    S = 0.55*doc_n + 0.45*(infra_n ** 1.3)

    p_injury = float(max(0.12, min(0.85, 0.65 - 0.35*S)))
    if float(rng.random()) >= p_injury:
        return ("NONE", 0)

    weights = _inj_np.array([0.60, 0.30, 0.09, 0.01], dtype=float)
    if float(rng.random()) < (0.65 * S):
        shifted = _inj_np.array([weights[0] + weights[1]*0.65*S,
                                 weights[1]*(1-0.65*S) + weights[2]*0.65*S,
                                 weights[2]*(1-0.65*S) + weights[3]*0.65*S,
                                 weights[3]*(1-0.65*S)], dtype=float)
        weights = shifted / shifted.sum()
    idx = int(rng.choice(4, p=(weights/weights.sum())))
    severities = ("LIGHT","MODERATE","SERIOUS","SEVERE")
    sev = severities[idx]

    if sev == "LIGHT":
        lo, hi = 1, 7
    elif sev == "MODERATE":
        lo, hi = 14, 42
    elif sev == "SERIOUS":
        lo, hi = 42, 84
    else:
        lo, hi = 90, 270

    base_days = int(rng.integers(lo, hi+1))
    eff = base_days * (1.0 - 0.35*S) * float(_inj_np.exp(rng.normal(0.0, 0.15)))
    return (sev, int(max(0, round(eff))))

def _annotate_falls_with_injuries(falls_df, roster, rng):
    """Return a copy of falls_df with columns \'Kontuzja (rodzaj)\', \'Kontuzja (dni)\',
    plus \'ΔUM (kontuzja)\' and \'ΔForma (kontuzja)\' per upadek."""
    if falls_df is None or getattr(falls_df, "empty", True) or _inj_pd is None or _inj_np is None:
        return falls_df
    _ensure_medical_maps_loaded()
    # Build name->sex map from roster
    sex_col = None
    for c in ("Sex","Płeć","Plec"):
        if c in roster.columns:
            sex_col = c; break
    name_col = "Zawodnik" if "Zawodnik" in roster.columns else None
    nat_col = "Kraj" if "Kraj" in roster.columns else None
    if name_col is None or nat_col is None:
        out = falls_df.copy()
        out["Kontuzja (rodzaj)"] = "NONE"
        out["Kontuzja (dni)"] = 0
        return out

    # Quick lookup by name: Sex
    r2 = roster[[name_col, sex_col]].copy() if sex_col else roster[[name_col]].copy()
    if sex_col:
        r2[sex_col] = r2[sex_col].astype(str).str.upper().str[:1]
    name_to_sex = dict(zip(r2[name_col].astype(str), r2[sex_col] if sex_col else [""]*len(r2)))

    # Prepare output arrays
    sev_list, days_list = [], []
    _sex_list, _doc_list, _infra_list = [], [], []
    _weeks_list, _d_um_list, _d_fr_list = [], [], []

    for _, row in falls_df.iterrows():
        nat = str(row.get("Kraj","")).strip().upper()
        name = str(row.get("Zawodnik",""))
        sex = (name_to_sex.get(name,"") or "").upper()
        doc_map = _DOCTOR_MAP_M if sex == "M" else _DOCTOR_MAP_W
        doctor = float(doc_map.get(nat, 50.0)) if isinstance(doc_map, dict) else 50.0
        infra = int((_INFRA_MAP or {}).get(nat, 3))
        print(f"DEBUG INJURY: {name} | nat={nat} | infra={infra} | doctor={doctor} | _INFRA_MAP keys sample={list((_INFRA_MAP or {}).keys())[:5]}")
        # collect meta columns for GUI
        try:
            _sex_list.append(sex)
            _doc_list.append(int(round(doctor)))
            _infra_list.append(int(infra))
        except NameError:
            _sex_list = [sex]
            _doc_list = [int(round(doctor))]
            _infra_list = [int(infra)]
        sev, dd = _injury_roll__core(infra, doctor, rng)
        sev_list.append(sev)
        days_list.append(dd)
        # compute week buckets: <=5 ->0, 6-12 ->1, 13-19 ->2, 20-26 ->3, etc.
        _weeks = 0 if (dd is None or dd <= 5) else (1 + int((dd - 6) // 7))
        try:
            _weeks_list.append(_weeks)
        except NameError:
            _weeks_list = [_weeks]
        d_um, d_fr = _injury_penalty_um_forma(dd, rng)
        try:
            _d_um_list.append(d_um)
            _d_fr_list.append(d_fr)
        except NameError:
            _d_um_list = [d_um]
            _d_fr_list = [d_fr]

    out = falls_df.copy()
    out["Kontuzja (rodzaj)"] = _inj_pd.Series(sev_list, index=out.index, dtype=object)
    out["Kontuzja (dni)"] = _inj_pd.Series(days_list, index=out.index, dtype=int)
    try:
        out["ΔUM (kontuzja)"] = _inj_pd.Series(_d_um_list, index=out.index, dtype=int)
        out["ΔForma (kontuzja)"] = _inj_pd.Series(_d_fr_list, index=out.index, dtype=int)
    except Exception:
        out["ΔUM (kontuzja)"] = 0
        out["ΔForma (kontuzja)"] = 0
    try:
        out["Długość kontuzji (WEEK)"] = _inj_pd.Series(_weeks_list, index=out.index, dtype=int)
    except Exception:
        out["Długość kontuzji (WEEK)"] = 0
    try:
        out["Płeć"] = _inj_pd.Series(_sex_list, index=out.index, dtype=object)
        out["Lekarz"] = _inj_pd.Series(_doc_list, index=out.index, dtype=int)
        out["Infrastruktura"] = _inj_pd.Series(_infra_list, index=out.index, dtype=int)
    except Exception:
        out["Płeć"] = out.get("Płeć", "M")
        out["Lekarz"] = out.get("Lekarz", 50)
        out["Infrastruktura"] = out.get("Infrastruktura", 3)
    return out

def _injury_penalty_um_forma(days, rng):
    """
    Map length of injury (days) to drops in UM and Forma.
    Target: ~21 days -> ~3-4 UM and ~7-9 Forma.
    Returns tuple: (delta_um, delta_forma) as NEGATIVE integers.
    """
    if days is None or days <= 0:
        return (0, 0)
    base_um = 3.5     # ~3-4 for 21 days
    base_forma = 8.0  # ~7-9 for 21 days
    scale = (float(days) / 21.0) ** 0.9
    noise = float(np.exp(np.random.default_rng().normal(0.0, 0.12)))
    um  = int(max(0, round(base_um * scale * noise)))
    fr  = int(max(0, round(base_forma * scale * noise)))
    # soft caps to avoid runaway on very long injuries
    um_cap = int(min(15, round(0.20 * days)))     # ≤ 1 per 5 days, max 15
    fr_cap = int(min(35, round(0.45 * days)))     # ≤ ~1 per 2.2 days, max 35
    um  = min(um, um_cap)
    fr  = min(fr, fr_cap)
    return (-um, -fr)
# =================== END: INJURY / MEDICAL MAPS – HELPERS ===================


