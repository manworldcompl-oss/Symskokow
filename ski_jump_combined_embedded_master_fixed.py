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

try:
    from db_viewer_gui_embedded import build_gui as build_db_viewer_gui
except Exception as _e_db_viewer:
    build_db_viewer_gui = None
    print("[WARN] db_viewer_gui_embedded niedostępny:", _e_db_viewer)
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

def detect_current_season_num(app_dir: Path):
    """
    Wykrywa numer bieżącego sezonu na podstawie folderów ./S<nr>/ w app_dir,
    a w razie braku takich folderów - na podstawie najwyższego tagu 'S<nr>'
    znalezionego w plikach .py w app_dir. Zwraca int albo None.
    """
    import re as _re3

    season_nums = []
    try:
        for p in app_dir.iterdir():
            if p.is_dir():
                m = _re3.fullmatch(r"S(\d+)", p.name)
                if m:
                    season_nums.append(int(m.group(1)))
    except Exception:
        pass

    if season_nums:
        return max(season_nums)

    nums = set()
    for f in app_dir.glob("*.py"):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        nums.update(int(x) for x in _re3.findall(r"S(\d+)", text))
    return max(nums) if nums else None


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

    def _ask_season_numbers(self, detected_cur):
        """
        Okno z polami 'Bieżący sezon' i 'Nowy sezon' (numery, bez 'S'),
        wstępnie wypełnionymi na podstawie auto-detekcji, ale w pełni
        edytowalnymi przez użytkownika. Zwraca (cur, nxt) albo None,
        jeśli użytkownik kliknął Anuluj / zamknął okno.
        """
        win = tk.Toplevel(self)
        win.title("Nowy sezon")
        try: win.transient(self)
        except Exception: pass
        try: win.grab_set()
        except Exception: pass

        frm = ttk.Frame(win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        default_cur = detected_cur if detected_cur is not None else ""
        default_new = (detected_cur + 1) if detected_cur is not None else ""

        ttk.Label(frm, text="Bieżący sezon (numer, np. 50):").grid(row=0, column=0, sticky="w", pady=4)
        var_cur = tk.StringVar(value=str(default_cur))
        ttk.Entry(frm, textvariable=var_cur, width=10).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(frm, text="Nowy sezon (numer, np. 51):").grid(row=1, column=0, sticky="w", pady=4)
        var_new = tk.StringVar(value=str(default_new))
        ttk.Entry(frm, textvariable=var_new, width=10).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        if detected_cur is None:
            ttk.Label(
                frm,
                text="(nie udało się wykryć numeru sezonu automatycznie - podaj go ręcznie)",
                foreground="#a00",
            ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 4))

        result = {"ok": False}

        def _ok():
            result["ok"] = True
            win.destroy()

        def _cancel():
            result["ok"] = False
            win.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btns, text="Dalej", command=_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Anuluj", command=_cancel).pack(side=tk.LEFT, padx=4)

        win.bind("<Return>", lambda e: _ok())
        win.bind("<Escape>", lambda e: _cancel())

        win.wait_window()

        if not result["ok"]:
            return None

        from tkinter import messagebox
        try:
            cur = int(var_cur.get().strip())
            nxt = int(var_new.get().strip())
        except Exception:
            messagebox.showerror("Nowy sezon", "Podaj poprawne numery sezonów (liczby całkowite).", parent=self)
            return None
        if cur == nxt:
            messagebox.showerror("Nowy sezon", "Bieżący i nowy sezon muszą się różnić.", parent=self)
            return None
        return cur, nxt

    def migrate_season_files(self):
        """
        Zamienia tag bieżącego sezonu (np. 'S51') na nowy (np. 'S51') we
        WSZYSTKICH plikach .py leżących w tym samym folderze co ten plik
        (bez podfolderów typu ./S51/ i bez plików .csv).
        Numery sezonów są proponowane na podstawie auto-detekcji
        (folder ./S<nr>/), ale użytkownik może je zmienić w oknie dialogowym.
        Przed nadpisaniem każdy plik dostaje kopię '<nazwa>.py.bak_S<nr>'.
        """
        from tkinter import messagebox

        detected_cur = detect_current_season_num(APP_DIR)

        picked = self._ask_season_numbers(detected_cur)
        if picked is None:
            return
        cur, nxt = picked

        old_tag, new_tag = f"S{cur}", f"S{nxt}"

        # 2) Znajdź pliki .py w tym folderze (nierekurencyjnie), które zawierają stary tag
        hits = []
        for f in sorted(APP_DIR.glob("*.py")):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            n = text.count(old_tag)
            if n > 0:
                hits.append((f, n, text))

        if not hits:
            messagebox.showinfo("Nowy sezon", f"Nie znaleziono wystąpień '{old_tag}' w plikach .py.", parent=self)
            return

        # 3) Potwierdzenie z podglądem
        listing = "\n".join(f"• {f.name}: {n}x" for f, n, _ in hits)
        ok = messagebox.askyesno(
            "Nowy sezon",
            f"Zmienić '{old_tag}' → '{new_tag}' w {len(hits)} plikach .py "
            f"(w folderze {APP_DIR.name}, bez podfolderów i CSV)?\n\n{listing}\n\n"
            f"Przed zapisem zostaną utworzone kopie '*.py.bak_{old_tag}'.",
            parent=self,
        )
        if not ok:
            return

        # 4) Wykonaj zamianę + backup
        done, errors = [], []
        for f, n, text in hits:
            try:
                bak = f.with_name(f.name + f".bak_{old_tag}")
                if not bak.exists():
                    bak.write_text(text, encoding="utf-8")
                f.write_text(text.replace(old_tag, new_tag), encoding="utf-8")
                done.append(f"{f.name} ({n}x)")
            except Exception as e:
                errors.append(f"{f.name}: {e}")

        msg = f"Zamieniono '{old_tag}' → '{new_tag}' w plikach:\n" + "\n".join(done)
        if errors:
            msg += "\n\nBłędy:\n" + "\n".join(errors)
        msg += "\n\nPamiętaj, że ten plik (combined) zostanie w pełni odświeżony po restarcie programu."
        messagebox.showinfo("Nowy sezon – gotowe", msg, parent=self)

    def restart_app(self):
        """
        Odświeża WSZYSTKIE moduły - efektywnie restartuje cały program
        (świeże wczytanie silnika, wszystkich zakładek/embedded GUI itd.),
        tak jakby został odpalony od nowa.
        """
        from tkinter import messagebox

        ok = messagebox.askyesno(
            "Odśwież wszystkie moduły",
            "To zamknie i ponownie uruchomi cały program, żeby świeżo wczytać "
            "WSZYSTKIE moduły (silnik, wszystkie zakładki/pliki .py).\n"
            "Niezapisane zmiany w otwartych zakładkach zostaną utracone.\n\n"
            "Kontynuować?",
            parent=self,
        )
        if not ok:
            return

        import os, sys, subprocess

        # Uruchamiamy NOWĄ, niezależną instancję programu, a dopiero potem
        # zamykamy tę. os.execv() nie nadaje się tu - przy starcie dwuklikiem
        # (bez konsoli, np. pythonw.exe) potrafił całkowicie zabić proces
        # bez odpalenia nowego okna.
        try:
            subprocess.Popen([sys.executable] + sys.argv, cwd=str(APP_DIR))
        except Exception as e:
            messagebox.showerror(
                "Odśwież wszystkie moduły",
                f"Nie udało się uruchomić nowej instancji programu:\n{e}",
                parent=self,
            )
            return

        # Natychmiastowe, "twarde" zamknięcie - bez tego SystemExit/Tk
        # potrafi się dziwnie zachować wywołane z wnętrza callbacku przycisku.
        os._exit(0)

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

        # --- Actions at top (jeden wiersz, IND/TEAM ścieżki schowane w dialogu) ---
        ttk.Button(top, text="Załaduj IND", command=self.load_ind).pack(side=tk.LEFT)
        ttk.Button(top, text="Załaduj TEAM", command=self.load_team).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Załaduj oba", command=self.load_both).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Odśwież silnik", command=self.refresh_engine).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="⚙ Ścieżki IND/TEAM…", command=self.open_paths_dialog).pack(side=tk.LEFT, padx=6)

        ttk.Separator(top, orient="vertical").pack(side=tk.LEFT, fill="y", padx=10, pady=2)

        _cur_season = detect_current_season_num(APP_DIR)
        if _cur_season is not None:
            _season_label = f"🆕 Nowy sezon (S{_cur_season}→S{_cur_season + 1}, pliki .py)"
        else:
            _season_label = "🆕 Nowy sezon (pliki .py)"

        ttk.Button(top, text=_season_label,
                   command=self.migrate_season_files).pack(side=tk.LEFT)
        ttk.Button(top, text="🔄 Odśwież wszystkie moduły (restart)",
                   command=self.restart_app).pack(side=tk.LEFT, padx=(8, 0))

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

        # --- PRZEGLĄDARKA BAZY MANAGER SKOKÓW ---
        self.tab_db_viewer = ttk.Frame(self.nb)
        self.nb.add(self.tab_db_viewer, text="Baza danych")
        if build_db_viewer_gui:
            try:
                build_db_viewer_gui(self.tab_db_viewer).pack(fill=tk.BOTH, expand=True)
            except Exception:
                import traceback as _tb
                print("[WARN] db_viewer_gui_embedded blad inicjalizacji:", _tb.format_exc())
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
            default_hills = APP_DIR / "S51/Skocznie S51.csv"
        except Exception:
            default_hills = None

        self.hills_tab = HillsTab(
            self.tab_hills,
            default_hills=Path("S51/Skocznie S51.csv"),
            default_infra=Path("S51/Infrastruktura S51.csv"),
            default_complexes=Path("S51/Kompleksy S51.csv"),
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



    def open_paths_dialog(self):
        """Okno z polami ścieżek IND/TEAM (domyślnie schowane, żeby pasek na górze był krótszy)."""
        win = tk.Toplevel(self)
        win.title("Ścieżki IND / TEAM")
        try: win.transient(self)
        except Exception: pass
        try: win.grab_set()
        except Exception: pass

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="IND:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.ind_path, width=60).grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(frm, text="Wskaż…", command=self.pick_ind).grid(row=0, column=2, pady=4)

        ttk.Label(frm, text="TEAM:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.team_path, width=60).grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(frm, text="Wskaż…", command=self.pick_team).grid(row=1, column=2, pady=4)

        frm.columnconfigure(1, weight=1)

        ttk.Button(frm, text="Zamknij", command=win.destroy).grid(row=2, column=0, columnspan=3, pady=(10, 0))

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