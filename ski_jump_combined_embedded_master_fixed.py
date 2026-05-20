#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import importlib.util
import types
from pathlib import Path
from hills_tab import HillsTab
import json
import platform
import traceback
import time

import pandas as pd
import tkinter as tk
from tkinter import ttk

FLAGS_DIR = Path("./flags")
# --- KALENDARZE ---
try:
    from calendars_gui_embedded import build_gui as build_calendars_gui
except Exception as _e_cal_gui:
    build_calendars_gui = None
    print("[WARN] calendars_gui_embedded niedostępny:", _e_cal_gui)
# ==== BEGIN: Editor helpers for "Baza zawodników (EDYCJA)" ====
PREFERRED_COL_ORDER = [
    "Zawodnik","Kraj","Płeć","JUN/SEN","Wiek","UM","Forma","PrawoStartu","Kontuzja"
]

try:
    from academy_gui_embedded import build_academies_root
except Exception as _e_acad:
    build_academies_root = None
    print("[WARN] academy_gui_embedded niedostępny:", _e_acad)

try:
    from ranking_fis_gui_embedded import build_gui as build_fis_ranking_gui
except Exception as _e_fis:
    build_fis_ranking_gui = None
    print("[WARN] ranking_fis_gui_embedded niedostępny:", _e_fis)

try:
    from prizes_gui_embedded import build_gui as build_prizes_gui
except Exception as _e_prizes:
    build_prizes_gui = None
    print("[WARN] prizes_gui_embedded niedostępny:", _e_prizes)

def _canonicalize_headers_editor(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=PREFERRED_COL_ORDER)
    import unicodedata, re as _re2
    def _norm(s: str) -> str:
        s = str(s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = _re2.sub(r"[^a-z0-9/]+", "", s)
        return s
    canon = {
        "zawodnik":"Zawodnik","name":"Zawodnik",
        "kraj":"Kraj","country":"Kraj",
        "plec":"Płeć","sex":"Płeć",
        "junsen":"JUN/SEN",
        "wiek":"Wiek","age":"Wiek",
        "um":"UM","forma":"Forma",
        "prawostartu":"PrawoStartu",
        "kontuzja":"Kontuzja","injury":"Kontuzja",
    }
    cols = []
    for c in df.columns:
        cols.append(canon.get(_norm(c), str(c)))
    out = df.copy(); out.columns = cols
    order = [c for c in PREFERRED_COL_ORDER if c in out.columns]
    tail  = [c for c in out.columns if c not in order]
    return out[order + tail].copy()

class EditableTable(ttk.Frame):
    def __init__(self, parent, df=None, height=24):
        super().__init__(parent)
        self._tree = ttk.Treeview(self, show="headings", height=height)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._hsb = ttk.Scrollbar(self, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=self._vsb.set, xscrollcommand=self._hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        self._vsb.grid(row=0, column=1, sticky="ns")
        self._hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1); self.grid_columnconfigure(0, weight=1)
        self._editor=None; self._editing_info=None
        self.set_dataframe(pd.DataFrame() if df is None else df)
        self._tree.bind("<Double-1>", self._begin_edit)
        self._tree.bind("<Return>", self._confirm_edit)
        self._tree.bind("<Escape>", self._cancel_edit)

    def set_dataframe(self, df: pd.DataFrame):
        self._df = pd.DataFrame() if df is None else df.copy()
        self._tree["columns"] = list(self._df.columns)
        for c in self._df.columns:
            self._tree.heading(c, text=c)
            try:
                width = max(60, min(240, int(self._df[c].astype(str).map(len).max() * 8)))
            except Exception:
                width = 100
            anchor = tk.E if str(self._df[c].dtype).startswith(("int","float")) else tk.W
            self._tree.column(c, width=width, anchor=anchor, stretch=False)
        for iid in self._tree.get_children(): self._tree.delete(iid)
        for _, row in self._df.iterrows():
            self._tree.insert("", "end", values=[row.get(c, "") for c in self._df.columns])

    def dataframe(self) -> pd.DataFrame:
        cols = list(self._tree["columns"]); rows = []
        for iid in self._tree.get_children():
            vals = self._tree.item(iid, "values")
            rows.append({c: vals[i] if i < len(vals) else "" for i, c in enumerate(cols)})
        out = pd.DataFrame(rows, columns=cols)
        for c in ("Wiek","UM","Forma","PrawoStartu","Kontuzja"):
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors="ignore")
        return out

    def _begin_edit(self, event):
        if self._tree.identify("region", event.x, event.y) != "cell": return
        row = self._tree.identify_row(event.y); col_id = self._tree.identify_column(event.x)
        if not row or not col_id: return
        try: col_idx = int(col_id[1:]) - 1
        except Exception: return
        cols = list(self._tree["columns"])
        if col_idx<0 or col_idx>=len(cols): return
        col = cols[col_idx]; bbox = self._tree.bbox(row, col_id)
        if not bbox: return
        x,y,w,h = bbox; values = self._tree.item(row, "values"); cur = values[col_idx] if col_idx < len(values) else ""
        self._cancel_edit()
        self._editor = tk.Entry(self._tree); self._editor.insert(0, str(cur)); self._editor.select_range(0, tk.END)
        self._editor.place(x=x,y=y,width=w,height=h); self._editor.focus_set(); self._editing_info=(row,col)
        self._editor.bind("<FocusOut>", lambda e: self._confirm_edit())

    def _confirm_edit(self, event=None):
        if not self._editor or not self._editing_info: return
        row, col = self._editing_info; text = self._editor.get()
        cols = list(self._tree["columns"]); values = list(self._tree.item(row, "values"))
        try: idx = cols.index(col)
        except ValueError: idx = -1
        if idx >= 0:
            if idx >= len(values): values.extend([""]*(idx-len(values)+1))
            values[idx] = text; self._tree.item(row, values=values)
        self._cancel_edit()

    def _cancel_edit(self, event=None):
        if self._editor is not None:
            try: self._editor.destroy()
            except Exception: pass
        self._editor=None; self._editing_info=None

    def add_empty_row(self):
        cols=list(self._tree["columns"]); self._tree.insert("", "end", values=["" for _ in cols])

    def delete_selected(self):
        for iid in self._tree.selection(): self._tree.delete(iid)
# ==== END: Editor helpers ====

# === Helpers: paths config + robust import ===
APP_DIR = Path(__file__).parent
CFG = APP_DIR / "combined_config.json"

def load_cfg():
    try:
        return json.loads(CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_cfg(ind_path, team_path):
    try:
        CFG.write_text(json.dumps({"ind": ind_path, "team": team_path}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def import_from(path: Path):
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"Nie znaleziono pliku: {path}")
    
    mod_name = f"{Path(path).stem}_{int(time.time()*1000)}"
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    
    if spec is None or spec.loader is None:
        raise ImportError(f"Nie można przygotować importu z pliku: {path}")
    
    mod = importlib.util.module_from_spec(spec)
    
    # --- TA CZĘŚĆ NAPRAWIA TWÓJ BŁĄD ---
    # Zamiast pozwolić loaderowi decydować o kodowaniu, 
    # sami wczytujemy kod jako UTF-8 i wykonujemy go w kontekście modułu.
    try:
        # Próbujemy odczytać jako UTF-8, ignorując drobne błędy znaków
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
        exec(code, mod.__dict__)
    except Exception:
        # Fallback do standardowego ładowania
        spec.loader.exec_module(mod)
    # ----------------------------------

    if not hasattr(mod, "build_gui"):
        raise AttributeError(f"{Path(path).name} nie udostępnia funkcji build_gui(parent)")
    return mod
# === End helpers ===

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
APP_DIR = Path(__file__).resolve().parent

IND_PATH = APP_DIR / "ski_jump_gui_full_embedded.py"
TEAM_PATH = APP_DIR / "team_competition_gui_embedded.py"

class Combined(tk.Tk):
    def refresh_engine(self):
        import importlib, sys, traceback
        from tkinter import messagebox

        # Moduły, które warto przeładować (silnik + ewentualne zależności z TEAM/KO64)
        targets = [
            "ski_jump_simulator_random_v6",
            "team_competition_display2rows_v3_fix",
            "ko64_bracket",
        ]

        reloaded = []
        try:
            for name in targets:
                if name in sys.modules:
                    importlib.reload(sys.modules[name])
                    reloaded.append(name)
                else:
                    # jeśli nie był jeszcze importowany – spróbuj zaimportować
                    try:
                        importlib.import_module(name)
                        reloaded.append(f"{name} (import)")
                    except Exception:
                        pass

            # Przebuduj obie zakładki, żeby GUI złapało świeże importy silnika
            self.load_both()

            messagebox.showinfo(
                "Odświeżono",
                "Przeładowano: " + (", ".join(reloaded) if reloaded else "brak modułów do przeładowania"),
                parent=self
            )
        except Exception:
            messagebox.showerror("Błąd odświeżania", traceback.format_exc(), parent=self)

    def _maximize_window(self):
        try:
            if platform.system() == "Windows":
                self.state("zoomed")
            else:
                self.attributes("-zoomed", True)
        except Exception:
            pass

    def _restore_window(self):
        try:
            self.state("normal")
            self.geometry("1200x800")
        except Exception:
            pass

    def __init__(self):
        super().__init__()
        self.title("Ski Jump – IND + TEAM (embedded)")
        self.geometry("1200x800")
        try:
            if platform.system() == "Windows":
                self.state("zoomed")
            else:
                self.attributes("-zoomed", True)
        except Exception:
            pass

        # --- Sztab (MEN/WOMEN)
        try:
            from staff_gui_embedded import build_gui as build_staff_gui
        except Exception as _e_staff:
            build_staff_gui = None
            print("[WARN] staff_gui_embedded niedostępny:", _e_staff)

        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        self.ind_path = tk.StringVar(value=str(IND_PATH))
        self.team_path = tk.StringVar(value=str(TEAM_PATH))

        ttk.Label(top, text="IND:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.ind_path, width=52).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(top, text="Wskaż…", command=self.pick_ind).pack(side=tk.LEFT, padx=6)

        ttk.Label(top, text="TEAM:", padding=(16,0)).pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.team_path, width=52).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(top, text="Wskaż…", command=self.pick_team).pack(side=tk.LEFT, padx=6)

        # --- Actions at top ---
        ttk.Button(top, text="Załaduj IND", command=self.load_ind).pack(side=tk.LEFT, padx=(16,0))
        ttk.Button(top, text="Załaduj TEAM", command=self.load_team).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Załaduj oba", command=self.load_both).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Odśwież silnik", command=self.refresh_engine).pack(side=tk.LEFT, padx=6)
        ttk.Separator(self).pack(fill=tk.X, padx=8, pady=(6,0))

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_hills = ttk.Frame(self.nb)
        self.tab_ind = ttk.Frame(self.nb)
        self.tab_team = ttk.Frame(self.nb)
        self.tab_db_edit = ttk.Frame(self.nb)
        self.tab_kalendarze = build_calendars_gui(self.nb)
        self.tab_cls = ttk.Frame(self.nb)
        self.tab_staff = (build_staff_gui(self.nb) if build_staff_gui else ttk.Frame(self.nb))
        self.nb.add(self.tab_hills, text="Skocznie")
        self.nb.add(self.tab_ind, text="IND – indywidualne")
        self.nb.add(self.tab_team, text="TEAM – drużynowe")
        self.nb.add(self.tab_db_edit, text="Baza zawodników (EDYCJA)")
        self.nb.add(self.tab_kalendarze, text="Kalendarze")
        self.nb.add(self.tab_cls, text="Klasyfikacje")
        self.nb.add(self.tab_staff, text="Sztab")
        # --- NAGRODY ---
        if build_prizes_gui:
            self.tab_prizes = build_prizes_gui(self.nb)
        else:
            self.tab_prizes = ttk.Frame(self.nb)
        # --- RANKING FIS ---
        if build_fis_ranking_gui:
            self.tab_fis = build_fis_ranking_gui(self.nb)
        else:
            self.tab_fis = ttk.Frame(self.nb)
        self.nb.add(self.tab_fis, text="Ranking FIS")
        self.nb.add(self.tab_prizes, text="Nagrody")
        try:
            from players_db_gui_embedded import build_gui  # <- ładujemy nasz moduł
            # wstawiamy gotowy frame do zakładki
            build_gui(self.tab_db_edit).pack(fill=tk.BOTH, expand=True)
        except Exception:
            from tkinter import messagebox
            import traceback
            messagebox.showerror("Baza zawodników – błąd", traceback.format_exc(), parent=self)

        try:
            cls_mod = import_from(Path("klasyfikacje_gui_embedded.py"))  # masz już helper import_from
            self.cls_frame = cls_mod.build_gui(self.tab_cls)
            self.cls_frame.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            import traceback; from tkinter import messagebox
            messagebox.showerror("Klasyfikacje", traceback.format_exc(), parent=self)

        try:
            default_hills = APP_DIR / "S45/Skocznie S45.csv"
        except Exception:
            default_hills = None

        self.hills_tab = HillsTab(
            self.tab_hills,
            default_hills=Path("S45/Skocznie S45.csv"),
            default_infra=Path("S45/Infrastruktura S45.csv"),
            default_complexes=Path("S45/Kompleksy S45.csv"),
            flags_dir=FLAGS_DIR,
        )
        self.hills_tab.pack(fill=tk.BOTH, expand=True)

        # --- AKADEMIE ---
        if build_academies_root:
            self.tab_academies = build_academies_root(self.nb)
        else:
            self.tab_academies = ttk.Frame(self.nb)

        self.nb.add(self.tab_academies, text="Akademie")

        # scroll o 1 jednostkę zamiast domyślnych 2 na Windows
        # bind_class nie zastępuje wbudowanego handlera Tcl – musimy nadpisać go przez tk.eval
        try:
            self.tk.eval('''
                bind Treeview <MouseWheel> {
                    if {%D > 0} {
                        %W yview scroll -1 units
                    } else {
                        %W yview scroll 1 units
                    }
                }
                bind Listbox <MouseWheel> {
                    if {%D > 0} {
                        %W yview scroll -1 units
                    } else {
                        %W yview scroll 1 units
                    }
                }
                bind Text <MouseWheel> {
                    if {%D > 0} {
                        %W yview scroll -1 units
                    } else {
                        %W yview scroll 1 units
                    }
                }
            ''')
        except Exception as _e:
            print(f"[WARN] scroll fix nieudany: {_e}")

        # --- Zakładka Obozy ---
        try:
            from camps_gui_embedded import build_gui as build_camps_gui
            self.tab_camps = build_camps_gui(self.nb)
            self.nb.add(self.tab_camps, text="Obozy")
        except Exception as e:
            print(f"[ERROR] Nie udało się załadować modułu Obozy: {e}")



    def pick_ind(self):
        p = filedialog.askopenfilename(filetypes=[("Python", "*.py"), ("All", "*.*")])
        if p:
            self.ind_path.set(p)
            try: save_cfg(self.ind_path.get(), self.team_path.get())
            except Exception: pass

    def pick_team(self):
        p = filedialog.askopenfilename(filetypes=[("Python", "*.py"), ("All", "*.*")])
        if p:
            self.team_path.set(p)
            try: save_cfg(self.ind_path.get(), self.team_path.get())
            except Exception: pass

    # --- DB editor tab ---
    def clear_tab(self, tab):
        for w in tab.winfo_children():
            w.destroy()

    def load_ind(self):
        self.clear_tab(self.tab_ind)
        try:
            mod = import_from(Path(self.ind_path.get()))
            mod.build_gui(self.tab_ind)
            save_cfg(self.ind_path.get(), self.team_path.get())
        except Exception:
            from tkinter import messagebox
            messagebox.showerror("IND – błąd", traceback.format_exc(), parent=self)

    def load_team(self):
        self.clear_tab(self.tab_team)
        try:
            # Importujemy moduł
            mod = import_from(Path(self.team_path.get()))
            
            # WYMUSZENIE FLAG:
            import flags_cache
            mod.FLAG_CACHE = flags_cache.FLAG_CACHE
            
            mod.build_gui(self.tab_team)
            save_cfg(self.ind_path.get(), self.team_path.get())
        except Exception:
            from tkinter import messagebox
            messagebox.showerror("TEAM – błąd", traceback.format_exc(), parent=self)

    def load_both(self):
        self.load_ind()
        self.load_team()

if __name__ == "__main__":
    Combined().mainloop()