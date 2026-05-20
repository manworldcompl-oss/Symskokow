
# === Global GUI-friendly exception hook (auto-log + message box + pause) ===


import sys, traceback
def _gui_excepthook(exctype, value, tb):
    tb_txt = ''.join(traceback.format_exception(exctype, value, tb))
    try:
        with open('team_gui_error.log', 'w', encoding='utf-8') as f:
            f.write(tb_txt)
    except Exception:
        pass
    try:
        # Try to show a Tkinter message box (even before GUI exists)
        import tkinter as tk
        from tkinter import messagebox
        _root = tk.Tk(); _root.withdraw()
        messagebox.showerror("Błąd programu", tb_txt[-4000:])
        _root.destroy()
    except Exception:
        pass
    try:
        # Keep console open when launched by double-click
        print(tb_txt, file=sys.stderr, flush=True)
        input("Wciśnij Enter, aby zamknąć...")
    except Exception:
        pass

sys.excepthook = _gui_excepthook
# === End hook ===
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import json
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

from players_db_gui_embedded import PlayerDBFrame  # roster editor GUI
import inspect
from tkinter import font as tkfont

# użyj silnika kontuzji z IND GUI (jeśli dostępny)
try:
    from ski_jump_gui_full_embedded import _annotate_falls_with_injuries
except Exception:
    _annotate_falls_with_injuries = None

# --- FLAGS: spójny helper ---
try:
    from flags_cache import FLAG_CACHE
    # WYMUSZENIE ŚCIEŻKI: 
    # Nawet jeśli obiekt istnieje, upewniamy się, że szuka w ./flags
    if FLAG_CACHE:
        from pathlib import Path
        FLAG_CACHE.folder = Path("./flags")
except Exception:
    FLAG_CACHE = None
    try:
        from pathlib import Path
        import tkinter as tk
        # Fallback: ręczna próba inicjalizacji, jeśli moduł flags_cache zawiedzie
        from flags_cache import _FlagCache
        FLAG_CACHE = _FlagCache("./flags")
    except Exception as e:
        print(f"[DEBUG] Krytyczny błąd inicjalizacji flag: {e}")

# === UNIWERSALNY WYSZUKIWACZ CSV: obsługa ./, folder pliku, ./S45/, ./S44/ ===
def _find_nearby_file(basename, alt_patterns=()):
    """
    Szuka pliku wg nazwy/wzorca w:
      - bieżącym katalogu,
      - folderze, w którym leży ten skrypt,
      - podfolderach 'S45' i 'S44' (dla obu powyższych).
    Zwraca pełną ścieżkę (str) lub None.
    """
    from pathlib import Path

    # zbuduj listę korzeni do przeszukania
    roots = [Path.cwd()]
    try:
        roots.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    # dodaj S45/ i S44/
    extra = []
    for r in list(roots):
        extra.extend([r / "S45", r / "S44"])
    roots = [p for p in (roots + extra) if p.exists()]

    # jeżeli dostał już istniejącą ścieżkę — oddaj
    try:
        p_in = Path(basename)
        if p_in.exists():
            return str(p_in)
    except Exception:
        pass

    patterns = [str(basename)] + [str(p) for p in (alt_patterns or [])]

    # 1) dokładna nazwa w każdym korzeniu
    low_name = str(basename).lower()
    for r in roots:
        cand = r / basename
        if cand.exists() and cand.is_file():
            return str(cand)
        for f in r.glob("*.csv"):
            try:
                if f.name.lower() == low_name:
                    return str(f)
            except Exception:
                continue

    # 2) wzorce glob (bez rekursji)
    for r in roots:
        for pat in patterns:
            for f in r.glob(pat):
                try:
                    if f.is_file():
                        return str(f)
                except Exception:
                    continue

    # 3) rekursja tylko w S45/S44 (gdy ktoś zrobił dodatkowe podfoldery)
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
    """
    Uniwersalne wczytywanie CSV/XLSX:
    - próbuje różne separatoy (; ,)
    - próbuje różne kodowania
    - awaryjnie próbuje Excela
    Zwraca DataFrame albo None.
    """
    import pandas as _pd
    last_err = None
    # Najpierw CSV ze średnikiem, potem przecinek; z fallbackiem enkodowania
    for sep in (";", ","):
        for enc in ("utf-8", "utf-8-sig", "cp1250", "latin1"):
            try:
                df = _pd.read_csv(path, sep=sep, engine="python", encoding=enc)
                print(f"DEBUG READ OK: {path} sep='{sep}' enc='{enc}' shape={getattr(df,'shape',None)}")
                return df
            except Exception as e:
                last_err = e
                continue
    # Na koniec spróbuj Excela (gdyby ktoś podał .xlsx)
    try:
        df = _pd.read_excel(path)
        print(f"DEBUG READ OK (xlsx): {path} shape={getattr(df,'shape',None)}")
        return df
    except Exception as e:
        last_err = e
        print("DEBUG READ FAIL:", path, "->", last_err)
        return None

def _countries_with_min_healthy_mw(min_m: int = 4, min_w: int = 4) -> set[str]:
    """
    Z pliku Zawodnicy S45gpt.csv zwraca kody krajów (Kraj),
    które mają co najmniej `min_m` zdrowych MEN i `min_w` zdrowych WOMEN
    (zdrowy = Kontuzja <= 0 lub NaN).
    """
    path = _find_nearby_file(
        "Zawodnicy S45gpt.csv",
        alt_patterns=["*Zawodnicy* S45*.csv", "*Zawodnicy*.csv"],
    )
    if not path:
        print("DEBUG CC: nie znaleziono pliku zawodników")
        return set()

    df = None
    last_err = None
    # próba automatycznego wykrycia separatora i kodowania
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            df_try = pd.read_csv(path, sep=None, engine="python", encoding=enc)
            df = df_try
            break
        except Exception as e:
            last_err = e
            df = None

    if df is None:
        try:
            df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
        except Exception:
            print("DEBUG CC: nie mogę wczytać CSV:", path, last_err)
            return set()

    # oczekiwane kolumny z Twojej bazy:
    # Zawodnik;Kraj;Płeć;JUN/SEN;Wiek;UM;Forma;PrawoStartu;Kontuzja
    for col in ("Kraj", "Płeć", "Kontuzja"):
        if col not in df.columns:
            print("DEBUG CC: brak wymaganej kolumny:", col, "w", list(df.columns))
            return set()

    tmp = df[["Kraj", "Płeć", "Kontuzja"]].copy()

    # normalizacja płci
    tmp["Płeć"] = (
        tmp["Płeć"]
        .astype(str)
        .str.upper()
        .str[:1]
        .map(lambda x: "W" if x == "F" else x)
    )

    # normalizacja kodu kraju
    tmp["Kraj"] = tmp["Kraj"].astype(str).str.upper().str.strip()

    # Kontuzja: NaN -> 0, liczba > 0 = kontuzjowany
    tmp["Kontuzja"] = pd.to_numeric(tmp["Kontuzja"], errors="coerce").fillna(0.0)

    # zdrowi
    tmp = tmp[tmp["Kontuzja"] <= 0.0]
    if tmp.empty:
        return set()

    grp = tmp.groupby(["Kraj", "Płeć"]).size().unstack(fill_value=0)

    ok_idx = grp[
        (grp.get("M", 0) >= min_m) &
        (grp.get("W", 0) >= min_w)
    ].index

    return {str(k).strip().upper() for k in ok_idx}

def _cc_q_summary_from_dir(dir_path):
    """
    Czyta kwalifikacje CC z katalogu dir_path, szukając plików:
      *_Q_CC_M*.csv -> MEN
      *_Q_CC_W*.csv -> WOMEN
      *_Q_CC_X*.csv -> MIX

    Zwraca DataFrame:
      Lp., Drużyna, Kraj, MEN, WOMEN, MIX, Suma
    posortowany malejąco po Suma.
    """
    import pandas as _pd
    from pathlib import Path

    dir_path = Path(dir_path)

    if not dir_path.is_dir():
        raise RuntimeError(f"Folder nie istnieje: {dir_path}")

    # --- lokalny reader CSV/XLSX, niezależny od reszty pliku ---
    def _read_tab_any_local(path):
        last_err = None
        path = Path(path)
        # próba auto-separatora
        for sep in (None, ";", ","):
            for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
                try:
                    if sep is None:
                        return _pd.read_csv(path, sep=None, engine="python", encoding=enc)
                    else:
                        return _pd.read_csv(path, sep=sep, engine="python", encoding=enc)
                except Exception as e:
                    last_err = e
        # awaryjnie Excel
        try:
            return _pd.read_excel(path)
        except Exception:
            raise RuntimeError(f"Nie mogę wczytać pliku {path}: {last_err}")

    def _col_local(df, aliases, prefix_ok=False):
        """Szuka kolumny po listce aliasów (case-insensitive, opcjonalnie prefix)."""
        if df is None or df.empty:
            return None
        low = {str(c).strip().lower(): c for c in df.columns}
        for a in aliases:
            a = a.lower()
            if a in low:
                return low[a]
        if prefix_ok:
            for a in aliases:
                a = a.lower()
                for k, orig in low.items():
                    if k.startswith(a):
                        return orig
        return None

    data = {}  # (Drużyna, Kraj) -> dict z polami MEN/WOMEN/MIX

    def _accumulate_for(patterns, col_name: str):
        nonlocal data
        found_any = False

        for pat in patterns:
            for p in dir_path.glob(pat):
                found_any = True
                df = _read_tab_any_local(p)
                if df is None or df.empty:
                    continue

                team_col = _col_local(df, ["Drużyna", "Druzyna", "Team", "Reprezentacja", "NATION"], prefix_ok=True)
                nat_col  = _col_local(df, ["Kraj", "NAT", "Kod", "Code"], prefix_ok=True)

                # preferuj "Suma", potem "Punkty"/"PTS", inaczej suma wszystkich liczbowych
                pts_col = _col_local(df, ["Suma", "SUMA", "Punkty", "PTS"], prefix_ok=True)

                if not team_col or not nat_col:
                    continue

                if pts_col:
                    pts_series = _pd.to_numeric(df[pts_col], errors="coerce").fillna(0.0)
                else:
                    tmp = df.copy()
                    drop_cols = {team_col, nat_col}
                    maybe_lp = _col_local(df, ["Lp.", "LP", "LP."], prefix_ok=True)
                    if maybe_lp:
                        drop_cols.add(maybe_lp)
                    for c in list(tmp.columns):
                        if c in drop_cols:
                            tmp.drop(columns=[c], inplace=True)
                    for c in list(tmp.columns):
                        tmp[c] = _pd.to_numeric(tmp[c], errors="coerce").fillna(0.0)
                    pts_series = tmp.sum(axis=1)

                for idx, row in df.iterrows():
                    team = str(row.get(team_col, "")).strip()
                    nat  = str(row.get(nat_col, "")).strip().upper()
                    if not team or not nat:
                        continue
                    pts = float(pts_series.loc[idx])
                    key = (team, nat)
                    if key not in data:
                        data[key] = {
                            "Drużyna": team,
                            "Kraj": nat,
                            "MEN": 0.0,
                            "WOMEN": 0.0,
                            "MIX": 0.0,
                        }
                    data[key][col_name] += pts

        return found_any

    found_m = _accumulate_for(["*_Q_CC_M*.csv"], "MEN")
    found_w = _accumulate_for(["*_Q_CC_W*.csv"], "WOMEN")
    found_x = _accumulate_for(["*_Q_CC_X*.csv"], "MIX")

    if not (found_m or found_w or found_x):
        raise RuntimeError(f"Nie znaleziono żadnych plików *_Q_CC_[MWX]*.csv w {dir_path}")

    if not data:
        return _pd.DataFrame(columns=["Lp.", "Drużyna", "Kraj", "MEN", "WOMEN", "MIX", "Suma"])

    rows = []
    for (_team, _nat), rec in data.items():
        men = float(rec.get("MEN", 0.0) or 0.0)
        wom = float(rec.get("WOMEN", 0.0) or 0.0)
        mix = float(rec.get("MIX", 0.0) or 0.0)
        total = men + wom + mix
        rows.append({
            "Drużyna": rec["Drużyna"],
            "Kraj": rec["Kraj"],
            "MEN": men,
            "WOMEN": wom,
            "MIX": mix,
            "Suma": total,
        })

    out = _pd.DataFrame(rows)
    out = out.sort_values("Suma", ascending=False, kind="stable").reset_index(drop=True)
    out.insert(0, "Lp.", range(1, len(out) + 1))
    return out

def _msc_q_summary_from_dir(dir_path, sex: str):
    """
    Czyta kwalifikacje MSC z katalogu dir_path:
      S45_Q_MSC_M.csv  (dla sex='M')
      S45_Q_MSC_W.csv  (dla sex='W')

    Zwraca DataFrame:
      Lp., Drużyna, Kraj, Punkty, Suma
    """
    import pandas as _pd
    from pathlib import Path

    from math import isnan  # na wszelki wypadek, choć raczej niepotrzebne

    sex = (str(sex or "M").upper() or "M")[0]
    suffix = "M" if sex == "M" else "W"

    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise RuntimeError(f"Folder nie istnieje: {dir_path}")

    fname = f"S45_Q_MSC_{suffix}.csv"
    path = dir_path / fname

    if not path.is_file():
        raise RuntimeError(f"Brak pliku kwalifikacji MSC: {path}")

    # używamy ogólnego czytnika z góry pliku
    df = _read_tab_any(path)
    if df is None or df.empty:
        raise RuntimeError(f"Pusty lub nieczytelny plik: {path}")

    # prosty cleanup nagłówków
    df.columns = [str(c).strip() for c in df.columns]

    # kolumny: drużyna / kraj
    def _pick_col(df, candidates):
        cols = [str(c) for c in df.columns]
        norm = [c.strip().lower() for c in cols]
        for cand in candidates:
            c_norm = str(cand).strip().lower()
            for i, cname in enumerate(norm):
                if cname == c_norm:
                    return cols[i]
        # prefiksowo
        for cand in candidates:
            c_norm = str(cand).strip().lower()
            for i, cname in enumerate(norm):
                if cname.startswith(c_norm):
                    return cols[i]
        return None

    team_col = _pick_col(df, ["Drużyna", "Druzyna", "Team", "Reprezentacja", "NATION"])
    nat_col  = _pick_col(df, ["Kraj", "NAT", "Kod", "Code"])

    if not team_col or not nat_col:
        raise RuntimeError(
            f"Nie znaleziono kolumn Drużyna/Kraj w {path} (mam: {list(df.columns)})"
        )

    # punkty: preferuj 'Punkty' / 'Suma', inaczej suma wszystkich liczbowych
    pts_col = _pick_col(df, ["Punkty", "PTS", "Suma"])

    if pts_col:
        pts_series = _pd.to_numeric(df[pts_col], errors="coerce").fillna(0.0)
    else:
        tmp = df.copy()
        drop_cols = {team_col, nat_col}
        lp_col = _pick_col(df, ["Lp.", "LP", "LP."])
        if lp_col:
            drop_cols.add(lp_col)
        for c in list(tmp.columns):
            if c in drop_cols:
                tmp.drop(columns=[c], inplace=True)
        for c in list(tmp.columns):
            tmp[c] = _pd.to_numeric(tmp[c], errors="coerce").fillna(0.0)
        pts_series = tmp.sum(axis=1)

    rows = []
    for idx, row in df.iterrows():
        team = str(row.get(team_col, "")).strip()
        nat = str(row.get(nat_col, "")).strip().upper()
        if not team or not nat:
            continue
        pts = float(pts_series.loc[idx])
        rows.append({
            "Drużyna": team,
            "Kraj": nat,
            "Punkty": pts,
        })

    if not rows:
        raise RuntimeError(f"Brak drużyn z punktami w {path}")

    out = _pd.DataFrame(rows)
    out = out.sort_values("Punkty", ascending=False, kind="stable").reset_index(drop=True)
    out.insert(0, "Lp.", range(1, len(out) + 1))
    out["Suma"] = out["Punkty"]

    print(f"[MSC-Q] gotowa tabela MSC-{sex}: {len(out)} wierszy")
    return out


_missing_flags_logged = set()

def _flag_cached(code: str):
    """
    Zwraca tk.PhotoImage dla kodu kraju (NAT).
    """
    if not code:
        return ""

    code = str(code).strip().upper()
    if not FLAG_CACHE:
        return ""

    # KLUCZOWA POPRAWKA: Wymuszamy ścieżkę do folderu, jeśli została zagubiona
    if hasattr(FLAG_CACHE, "folder"):
        FLAG_CACHE.folder = Path("./flags")

    try:
        img = FLAG_CACHE.get(code)
        if img:
            return img
        return FLAG_CACHE.blank() if hasattr(FLAG_CACHE, "blank") else ""
    except Exception as e:
        return ""

# --- importy z modułu silnika ---
_LAST_TEAM_CLASSIF = None
from team_competition_display2rows_v3_fix import (
    normalize_round_df,
    build_two_row_table,
    build_falls_sheet,
    compute_meter_value,
)

try:
    from team_competition_display2rows_v3_fix import simulate_round
except Exception:
    from ski_jump_simulator_random_v6 import simulate_round  # type: ignore

CONFIG_PATH = Path("team_competition_gui_config.json")

# ----------------------- UTIL -----------------------
def save_config(state: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showwarning("Uwaga", f"Nie udało się zapisać ustawień:\\n{e}")

def filter_kwargs_for(func, params: dict):
    sig = inspect.signature(func)
    allowed = set(sig.parameters.keys())
    return {k: v for k, v in params.items() if k in allowed}

def safe_autosize_columns(table: ttk.Treeview):
    try:
        fnt = tkfont.nametofont("TkDefaultFont")
    except Exception:
        fnt = None
    padding = 24
    for col in table["columns"]:
        maxw = (fnt.measure(col) if fnt else len(col) * 8) + padding
        for item in table.get_children():
            val = table.set(item, col)
            width_px = (fnt.measure(str(val)) if fnt else len(str(val)) * 8) + padding
            if width_px > maxw:
                maxw = width_px
        table.column(col, width=maxw)

# == GLOBALNY SCROLL DLA WSZYSTKICH COMBOBOXÓW (działa także gdy lista jest ZAMKNIĘTA) ==
def install_global_combobox_wheel(root):
    import tkinter as _tk
    def _bump_for(cmb, step):
        vals = tuple(cmb.cget("values") or ())
        if not vals:
            return
        i = _current_index_of(cmb)
        i = 0 if i < 0 else i
        _force_combobox_choice(cmb, i + step)

    def _find_parent_combobox(w):
        # wejdź po drzewie aż trafisz na TCombobox
        while w is not None:
            try:
                if w.winfo_class() == "TCombobox":
                    return w
            except Exception:
                break
            w = w.master
        return None

    def _route(event, step_from_delta=None):
        # znajdź widget pod kursorem, potem jego rodzica typu TCombobox
        try:
            x = root.winfo_pointerx()
            y = root.winfo_pointery()
            w = root.winfo_containing(x, y)
        except Exception:
            w = None
        cmb = _find_parent_combobox(w)
        if cmb is None:
            return  # nie pod comboboxem — przepuść dalej

        # normalizuj kierunek
        step = 0
        if step_from_delta is not None:
            step = step_from_delta
        else:
            # Windows/macOS
            try:
                step = -1 if event.delta > 0 else 1
            except Exception:
                step = 0
        if step == 0:
            return "break"

        _bump_for(cmb, step)
        return "break"

    # Windows/macOS
    root.bind_all("<MouseWheel>", _route, add="+")
    # Linux
    root.bind_all("<Button-4>", lambda e: _route(e, -1), add="+")
    root.bind_all("<Button-5>", lambda e: _route(e, +1), add="+")

def install_combobox_scroll_everywhere(root):
    """Globalny scroll dla WSZYSTKICH ttk.Combobox, także gdy są ZAMKNIĘTE.
    Działa dla Windows/macOS (<MouseWheel>) i X11/Linux (<Button-4/5>).
    """
    import tkinter as tk

    def _nearest_combobox(w):
        # idziemy w górę po rodzicach aż trafimy na TCombobox
        while w is not None:
            try:
                if w.winfo_class() == "TCombobox":
                    return w
            except Exception:
                break
            w = w.master
        return None

    def _bump(cmb, step):
        try:
            vals = tuple(cmb.cget("values") or ())
            if not vals:
                return "break"
            i = _current_index_of(cmb)
            if i < 0:
                i = 0
            _force_combobox_choice(cmb, i + step)
        except Exception:
            pass
        return "break"

    # Handler dla Windows/macOS (delta dodatnia w górę, ujemna w dół; czasem bywa 0, więc bierzemy znak)
    def _wheel_any(event):
        w = event.widget
        cmb = w if w.winfo_class() == "TCombobox" else _nearest_combobox(w)
        if cmb is None:
            return  # nie blokuj innych widgetów
        step = -1 if getattr(event, "delta", 0) > 0 else 1
        return _bump(cmb, step)

    # Handlery dla X11/Linux
    def _btn4(event):
        w = event.widget
        cmb = w if w.winfo_class() == "TCombobox" else _nearest_combobox(w)
        if cmb is None:
            return
        return _bump(cmb, -1)

    def _btn5(event):
        w = event.widget
        cmb = w if w.winfo_class() == "TCombobox" else _nearest_combobox(w)
        if cmb is None:
            return
        return _bump(cmb, +1)

    # 1) Bind KLASY dla TCombobox (gdy kursor nad comboboxem lub jego ramką)
    root.bind_class("TCombobox", "<MouseWheel>", _wheel_any, add="+")
    root.bind_class("TCombobox", "<Button-4>",  _btn4,      add="+")
    root.bind_class("TCombobox", "<Button-5>",  _btn5,      add="+")
    # 2) Bind KLASY dla TEntry (wewnętrzny edytor comboboxa, łapie kółko, gdy lista jest ZAMKNIĘTA)
    root.bind_class("TEntry",     "<MouseWheel>", _wheel_any, add="+")
    root.bind_class("TEntry",     "<Button-4>",   _btn4,      add="+")
    root.bind_class("TEntry",     "<Button-5>",   _btn5,      add="+")

# WSTAW RAZ, obok helperów do scrolla:
def _force_combobox_choice(cb, new_idx):
    vals = tuple(cb.cget("values") or ())
    if not vals:
        return
    # clamp
    new_idx = max(0, min(len(vals) - 1, int(new_idx)))
    # Najpewniejsze: ustaw wartość tekstową
    try:
        cb.set(str(vals[new_idx]))
    except Exception:
        # awaryjnie spróbuj current
        try: cb.current(new_idx)
        except Exception: pass
    # powiadom resztę GUI
    try:
        cb.event_generate("<<ComboboxSelected>>")
    except Exception:
        pass

def enable_combobox_wheel(cmb):
    """Scroll dla ttk.Combobox także gdy lista jest ZAMKNIĘTA."""
    def _bump(step):
        vals = tuple(cmb.cget("values") or ())
        if not vals:
            return
        i = _current_index_of(cmb)
        i = 0 if i < 0 else i
        ni = max(0, min(len(vals) - 1, i + step))
        if ni != i:
            cmb.current(ni)
            try: cmb.event_generate("<<ComboboxSelected>>")
            except Exception: pass

    # Windows/macOS trackpad/mysz
    def _on_wheel(e):
        # delta bywa 120, 1, 2... normalizujemy znak
        step = -1 if e.delta > 0 else 1
        _bump(step)
        return "break"

    # Linux
    def _on_b4(_): _bump(-1); return "break"
    def _on_b5(_): _bump(+1); return "break"

    # 1) Bind na sam combobox
    cmb.bind("<MouseWheel>", _on_wheel, add="+")
    cmb.bind("<Button-4>", _on_b4, add="+")
    cmb.bind("<Button-5>", _on_b5, add="+")
    cmb.bind("<Enter>", lambda e: cmb.focus_set(), add="+")  # żeby koło działało bez klikania

    # 2) Bind na wewnętrzny Entry (to on łapie kółko, gdy combobox jest zwinięty)
    entry = None
    for sub in (".entry", ".textbox"):  # różne tematy/wersje Tk
        try:
            entry = cmb.nametowidget(str(cmb) + sub)
            break
        except Exception:
            entry = None
    if entry is not None:
        entry.bind("<MouseWheel>", _on_wheel, add="+")
        entry.bind("<Button-4>", _on_b4, add="+")
        entry.bind("<Button-5>", _on_b5, add="+")
        entry.bind("<Enter>", lambda e: cmb.focus_set(), add="+")

    # 3) Upewnij się, że bind instancji jest pierwszy w bindtagach (przed klasą TCombobox)
    try:
        tags = list(cmb.bindtags())
        if tags and tags[0] != str(cmb):
            cmb.bindtags((str(cmb),) + tuple(t for t in tags if t != str(cmb)))
    except Exception:
        pass

    def _bump(step):
        vals = tuple(cmb.cget("values") or ())
        if not vals:
            return
        i = _current_index_of(cmb)
        i = 0 if i < 0 else i
        _force_combobox_choice(cmb, i + step)

def _cmb_values_tuple(cb):
    try:
        return tuple(cb.cget("values") or ())
    except Exception:
        return ()

def _current_index_of(cb):
    """Zwróć indeks bieżącej wartości nawet, jeśli ttk nie ustawił current()."""
    vals = _cmb_values_tuple(cb)
    if not vals:
        return -1
    try:
        i = cb.current()
        if i is not None and int(i) >= 0:
            return int(i)
    except Exception:
        pass
    # dopasuj po tekście w entry
    try:
        txt = cb.get()
        if txt:
            idx = next((k for k, v in enumerate(vals) if str(v) == str(txt)), -1)
            if idx >= 0:
                return idx
    except Exception:
        pass
    # fallback: nasz własny cache
    return getattr(cb, "_mw_idx", -1)

def _force_combobox_choice(cb, new_idx):
    vals = _cmb_values_tuple(cb)
    if not vals:
        return
    new_idx = max(0, min(len(vals) - 1, int(new_idx)))
    try:
        # ustaw tekst bezpośrednio i zapamiętaj nasz indeks
        cb.set(str(vals[new_idx]))
        cb._mw_idx = new_idx
    except Exception:
        try:
            cb.current(new_idx)
            cb._mw_idx = new_idx
        except Exception:
            pass
    try:
        cb.event_generate("<<ComboboxSelected>>")
    except Exception:
        pass

def add_scrollable_table(parent, columns, height=20):
    outer = ttk.Frame(parent, padding=(0, 8, 0, 8))
    inner = ttk.Frame(outer)
    table = ttk.Treeview(inner, columns=columns, show="headings", height=height)
    vsb = ttk.Scrollbar(inner, orient="vertical", command=table.yview)
    hsb = ttk.Scrollbar(inner, orient="horizontal", command=table.xview)
    table.configure(yscroll=vsb.set, xscroll=hsb.set)
    table.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    inner.rowconfigure(0, weight=1)
    inner.columnconfigure(0, weight=1)
    for col in columns:
        table.heading(col, text=col)
        table.column(col, anchor="center", stretch=True, minwidth=40)
    inner.pack(fill="both", expand=True)
    return outer, table

def _build_msc_q_table(parent, sex: str):
    """
    Tabela MSC Q: Lp. po lewej, Drużyna z flagą jako kolumna drzewa.
    """
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, padx=8, pady=8)

    # Definicja kolumn dla prawej strony (poza Lp. i Drużyną)
    cols_msc_right = [
        ("Kraj", 80, "center"),
        ("Punkty", 100, "center")
    ]

    # Tworzymy tabelę zamrożoną
    widget, ft = create_frozen_table(
        parent=frame,
        left_key="Lp.",
        left_title="Lp.",
        left_width=60,
        tree_text_key="Drużyna",
        tree_title="Drużyna",
        right_cols=cols_msc_right,
        image_from_row=lambda r: _flag_cached(str(r.get("Kraj", "")).strip()),
        height=24
    )
    widget.pack(fill="both", expand=True)

    # Mały helper updateujący dane
    def _populate_from_df(df):
        if df is None or df.empty:
            ft.clear()
            return
        # FrozenTable potrzebuje DataFrame do metody set_dataframe
        ft.set_dataframe(df)
        try:
            ft.autosize()
        except Exception:
            pass

    frame.tv = ft  # Referencja do obiektu FrozenTable
    frame.populate_from_df = _populate_from_df
    frame.sex = sex
    return frame

def add_country_table_with_flags(parent, height=22):
    """
    Lewa lista: 'Reprezentacja' (tekst + flaga w kolumnie #0) oraz 'Kraj' (kod).
    Zwraca (wrapper_frame, treeview). Używaj populate_country_rows_with_flags(...) do wypełniania.
    """
    outer = ttk.Frame(parent, padding=(0, 8, 0, 8))
    inner = ttk.Frame(outer)
    tv = ttk.Treeview(inner, show="tree headings", height=height, selectmode="extended")

    # kolumna-drzewo na etykietę z flagą
    tv.heading("#0", text="Reprezentacja")
    tv.column("#0", anchor="w", width=260, stretch=True)

    # kolumna z kodem kraju
    tv["columns"] = ("Kraj",)
    tv.heading("Kraj", text="Kraj")
    tv.column("Kraj", anchor="center", width=80, stretch=False)

    vsb = ttk.Scrollbar(inner, orient="vertical", command=tv.yview)
    hsb = ttk.Scrollbar(inner, orient="horizontal", command=tv.xview)
    tv.configure(yscroll=vsb.set, xscroll=hsb.set)

    tv.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    inner.rowconfigure(0, weight=1)
    inner.columnconfigure(0, weight=1)
    inner.pack(fill="both", expand=True)
    outer.pack_propagate(False)

    # trzymamy referencje do obrazków, inaczej Tk je odkurzy
    tv.img_refs = []

    return outer, tv

def add_player_table_with_flags(parent, columns=("Kraj","Odległość","Punkty"), text_heading="Zawodnik", height=22):
    """
    Tabela Treeview: #0 = Zawodnik (z flagą), a w kolumnach zwykłe wartości.
    Zwraca (wrapper_frame, tv). tv ma bufor obrazków w tv.img_refs.
    """
    outer = ttk.Frame(parent, padding=(0, 8, 0, 8))
    inner = ttk.Frame(outer)
    tv = ttk.Treeview(inner, show="tree headings", height=height, selectmode="extended")

    # kolumna-drzewo (zawodnik + flaga)
    tv.heading("#0", text=text_heading)
    tv.column("#0", anchor="w", width=260, stretch=True)

    tv["columns"] = columns
    for col in columns:
        tv.heading(col, text=col)
        tv.column(col, anchor="center", width=90, stretch=True)

    vsb = ttk.Scrollbar(inner, orient="vertical", command=tv.yview)
    hsb = ttk.Scrollbar(inner, orient="horizontal", command=tv.xview)
    tv.configure(yscroll=vsb.set, xscroll=hsb.set)

    tv.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    inner.rowconfigure(0, weight=1)
    inner.columnconfigure(0, weight=1)
    inner.pack(fill="both", expand=True)
    outer.pack_propagate(False)

    tv.img_refs = []  # trzymaj referencje do flag

    return outer, tv

def populate_player_rows_with_flags(tv: ttk.Treeview, df, name_col="Zawodnik", kraj_col="Kraj", cols_out=None):
    """
    Wypełnia tv rekordami: #0 = Zawodnik (tekst) + flaga(kod w kraj_col).
    cols_out = kolejność kolumn wartości (poza #0).
    Chroni się przed duplikatami nagłówków typu 'Kraj' -> Series zamiast skalaru.
    """
    import pandas as pd

    # helper: jeśli w komórce wyląduje Series (duplikat kolumn), weź pierwszy element
    def _first_scalar(v):
        try:
            if isinstance(v, pd.Series):
                return v.iloc[0]
        except Exception:
            pass
        return v

    # czyść tabelę i referencje do obrazków
    for iid in tv.get_children(""):
        tv.delete(iid)
    tv.img_refs[:] = []

    if df is None or getattr(df, "empty", True):
        return

    _df = pd.DataFrame(df).copy()

    # delikatne mapy nazw: „Punkty rundy” -> „Punkty”, „Odległość (m)” -> „Odległość”
    rename_map = {}
    if "Punkty" in (cols_out or ()):
        if "Punkty" not in _df.columns and "Punkty rundy" in _df.columns:
            rename_map["Punkty rundy"] = "Punkty"
    if "Odległość" in (cols_out or ()) and "Odległość" not in _df.columns and "Odległość (m)" in _df.columns:
        rename_map["Odległość (m)"] = "Odległość"
    if rename_map:
        _df.rename(columns=rename_map, inplace=True)

    # kolejność jak w tv, chyba że jawnie podano
    cols = list(cols_out or [c for c in tv["columns"]])

    for _, r in _df.iterrows():
        # KOD KRAJU z ochroną na Series
        code_raw = _first_scalar(r.get(kraj_col, ""))
        code = str(code_raw).strip().upper()
        img = _flag_cached(code)

        # trzymaj referencję BEZWZGLĘDNIE; blank też jest PhotoImage
        tv.img_refs.append(img or "")

        # wartości kolumn z ochroną na Series
        values = tuple(_first_scalar(r.get(c, "")) for c in cols)

        # nazwa zawodnika z ochroną na Series
        name_txt = _first_scalar(r.get(name_col, ""))
        tv.insert(
            "",
            "end",
            text=" " + str(name_txt),
            image=(img or ""),
            values=values
        )

def populate_country_rows_with_flags(tv: ttk.Treeview, codes_to_names: list[tuple[str, str]]):
    """codes_to_names = [(kod, pełna_nazwa), ...]"""
    # nic nie czyść po prawej – czyścimy tylko lewą listę
    for iid in tv.get_children(""):
        tv.delete(iid)
    tv.img_refs.clear()

    # sort po pełnej nazwie
    codes_to_names = sorted(codes_to_names, key=lambda x: (x[1] or "").lower())

    for code, full in codes_to_names:
        code = (code or "").strip().upper()
        full = full or code
        img = _flag_cached(code)
        tv.img_refs.append(img)
        # tekst w #0, obrazek = flaga, a w kolumnie „Kraj” sam kod
        tv.insert("", "end", text=" " + full, image=img, values=(code,))

def clear_table(table: ttk.Treeview):
    for i in table.get_children():
        table.delete(i)

def safe_name(text: str) -> str:
    return (text or "wynik").strip().replace("/", "-").replace("\\\\", "-").replace(":", "-")

def format_filename(pattern: str, hill: str) -> str:
    now = datetime.now()
    mapping = {
        "{hill}": safe_name(hill),
        "{YYYY}": now.strftime("%Y"),
        "{mm}": now.strftime("%m"),
        "{dd}": now.strftime("%d"),
        "{HH}": now.strftime("%H"),
        "{MM}": now.strftime("%M"),
        "{SS}": now.strftime("%S"),
    }
    out = pattern
    for k, v in mapping.items():
        out = out.replace(k, v)
    out = out.replace("{YYYY-mm-dd_HH-MM}", f"{now.strftime('%Y-%m-%d_%H-%M')}")
    return out + ".xlsx" if not out.lower().endswith(".xlsx") else out

def drop_fully_empty_rows(df: pd.DataFrame, cols):
    if df is None or df.empty:
        return df
    dfx = df.copy()
    mask_empty_text = dfx[cols].apply(lambda s: s.astype(str).str.strip().eq(""))
    mask_all_empty = (dfx[cols].isna() | mask_empty_text).all(axis=1)
    return dfx.loc[~mask_all_empty].reset_index(drop=True)

# --------- MAPOWANIE KOD -> PEŁNA NAZWA DRUŻYNY ---------
TEAM_NAME = {
"AND":"Andora","AUT":"Austria","BUL":"Bułgaria","CRO":"Chorwacja","CZE":"Czechy","EST":"Estonia","FIN":"Finlandia",
"FRA":"Francja","GRE":"Grecja","ESP":"Hiszpania","ISL":"Islandia","LAT":"Łotwa","GER":"Niemcy","NOR":"Norwegia",
"POL":"Polska","POR":"Portugalia","RUS":"Rosja","ROU":"Rumunia","SRB":"Serbia","SVK":"Słowacja","SLO":"Słowenia",
"SUI":"Szwajcaria","SWE":"Szwecja","UKR":"Ukraina","HUN":"Węgry","GBR":"Wielka Brytania","ITA":"Włochy","CHN":"Chiny",
"GEO":"Gruzja","IND":"Indie","JPN":"Japonia","KAZ":"Kazachstan","KGZ":"Kirgistan","KOR":"Korea Południowa","NEP":"Nepal",
"PAK":"Pakistan","TJK":"Tadżykistan","TUR":"Turcja","ARG":"Argentyna","BRA":"Brazylia","CHI":"Chile","PER":"Peru",
"GUA":"Gwatemala","HON":"Honduras","CAN":"Kanada","MEX":"Meksyk","NCA":"Nikaragua","USA":"Stany Zjednoczone","KEN":"Kenia",
"RPA":"Republika Południowej Afryki","TAN":"Tanzania","UGA":"Uganda","AUS":"Australia","FIJ":"Fidżi","NZL":"Nowa Zelandia",
"PNG":"Papua-Nowa Gwinea","LTU":"Litwa","CUB":"Kuba","BOL":"Boliwia","INA":"Indonezja","VAN":"Vanuatu","ALG":"Algieria",
"LIE":"Liechtenstein","HAI":"Haiti","COL":"Kolumbia","AZE":"Azerbejdżan","SAM":"Samoa","ETH":"Etiopia","NED":"Holandia",
"PHI":"Filipiny","VEN":"Wenezuela","DOM":"Dominikana","MAR":"Maroko","SOL":"Wyspy Salomona","ALB":"Albania","THA":"Tajlandia",
"ECU":"Ekwador","ESA":"Salwador","NGR":"Nigeria","KIR":"Kiribati","BEL":"Belgia","QAT":"Katar","JAM":"Jamajka",
"COD":"Demokratyczna Republika Konga","URU":"Urugwaj","NRU":"Nauru","IRL":"Irlandia","PAR":"Paragwaj","CMR":"Kamerun",
"IRI":"Iran","MHL":"Wyspy Marshalla","BAH":"Bahamy","BIH":"Bośnia i Hercegowina","SUR":"Surinam","TRI":"Trynidad i Tobago",
"AFG":"Afganistan","GHA":"Ghana","TGA":"Tonga","BLR":"Białoruś","GUY":"Gujana","PAN":"Panama","BAN":"Bangladesz",
"CIV":"Wybrzeże Kości Słoniowej","PLW":"Palau","MLT":"Malta","BRN":"Bahrajn","CRC":"Kostaryka","UZB":"Uzbekistan",
"SUD":"Sudan","FSM":"Mikronezja","MON":"Monako","YEM":"Jemen","BAR":"Barbados","EGY":"Egipt","TUV":"Tuvalu",
"RWA":"Rwanda","DEN":"Dania","MKD":"Macedonia Północna","ARM":"Armenia","ISR":"Izrael","VIE":"Wietnam","LBA":"Libia",
"MNE":"Czarnogóra","KSA":"Arabia Saudyjska","CYP":"Cypr","PUR":"Portoryko","SEN":"Senegal","SOM":"Somalia","LUX":"Luksemburg",
"IRQ":"Irak","MGL":"Mongolia","TUN":"Tunezja","MAD":"Madagaskar","LCA":"Saint Lucia","MYA":"Mjanma","SIN":"Singapur",
"SRI":"Sri Lanka","BIZ":"Belize","CHA":"Czad","MLI":"Mali","SMR":"San Marino","HKG":"Hongkong","UAE":"Zjednoczone Emiraty Arabskie",
"DMA":"Dominika","CPV":"Republika Zielonego Przylądka","SLE":"Sierra Leone","KOS":"Kosowo","FRO":"Wyspy Owcze","CUW":"Curacao",
"GRL":"Grenlandia","BUR":"Burkina Faso","COK":"Wyspy Cooka","MDA":"Mołdawia","MAS":"Malezja","TPE":"Tajwan",
"BER":"Bermudy","GUI":"Gwinea","MOZ":"Mozambik","GIB":"Gibraltar","BHU":"Bhutan","LAO":"Laos","SKN":"Saint Kitts and Nevis",
"GBS":"Gwinea Bissau","NAM":"Namibia"
}

def first_series(obj):
    """If a DF with duplicate-named columns is provided, take the first column as Series."""
    if isinstance(obj, pd.DataFrame):
        return obj.iloc[:, 0]
    return obj

def add_team_columns(df: pd.DataFrame, code_col_old: str) -> pd.DataFrame:
    """Zamień kolumnę z kodem na 'Kraj' i dodaj 'Drużyna' (pełna nazwa) przed nią.
       Odporne na duplikaty kolumn o tej samej nazwie.
    """
    if df is None or df.empty:
        return df
    df2 = df.copy()

    # Jeżeli są zduplikowane nazwy kolumn, wybieramy pierwszą kolumnę o danej nazwie
    if code_col_old in df2.columns:
        code_col_data = first_series(df2[code_col_old])
        df2["Kraj"] = code_col_data
        df2["Drużyna"] = code_col_data.map(lambda x: TEAM_NAME.get(str(x), str(x)))

        # Usuń ewentualne dodatkowe kolumny 'Drużyna' o tej samej nazwie (zachowaj pierwszą)
        cols = []
        seen = set()
        for c in df2.columns:
            if c not in seen:
                cols.append(c); seen.add(c)
        df2 = df2[cols]

        # Uporządkuj kolejność
        rest = [c for c in df2.columns if c not in ["Miejsce","Drużyna","Kraj"]]
        if "Miejsce" in df2.columns:
            df2 = df2[["Miejsce","Drużyna","Kraj"] + rest]
        else:
            df2 = df2[["Drużyna","Kraj"] + rest]
    return df2

def _export_team_champs_results(season: str, code: str):
    """
    Eksportuje pełną klasyfikację drużyn (2-wierszową) do pliku CSV.
    Format: Lp.;Drużyna;Kraj;Jumper1;Jumper2;Jumper3;Jumper4;Punkty
    """
    from tkinter import messagebox
    from pathlib import Path
    import pandas as pd

    # 1. Przygotowanie parametrów
    season = (season or "S45").strip() or "S45"
    code = (code or "").strip().upper()

    if not code:
        messagebox.showwarning("Mistrzostwa – TEAM", "Podaj kod pliku, np. WCH_M_TEAM.")
        return

    # 2. Pobranie danych z bufora globalnego
    df_src = globals().get("_LAST_TWO_ROWS_DATA")
    
    if df_src is None or not isinstance(df_src, pd.DataFrame) or df_src.empty:
        messagebox.showwarning(
            "Mistrzostwa – TEAM", 
            "Brak danych w podglądzie.\nUruchom najpierw konkurs TEAM."
        )
        return

    # 3. Kopia danych i przygotowanie struktury
    df_export = df_src.copy()

    # Maski dla wierszy głównych i wierszy z detalami (odległościami)
    mask_main = df_export["Miejsce"].astype(str).str.strip() != ""
    is_detail_row = df_export["Miejsce"].astype(str).str.strip() == ""

    # --- FORMATOWANIE WIERSZY GŁÓWNYCH ---
    # Lp. jako liczba całkowita (Integer)
    try:
        df_export.loc[mask_main, "Miejsce"] = (
            pd.to_numeric(df_export.loc[mask_main, "Miejsce"], errors='coerce')
            .fillna(0)
            .astype(int)
        )
    except Exception:
        pass

    # Wymuszenie pełnej nazwy drużyny na podstawie słownika TEAM_NAME
    if 'TEAM_NAME' in globals():
        df_export.loc[mask_main, "Drużyna"] = df_export.loc[mask_main, "Kraj"].map(
            lambda x: TEAM_NAME.get(str(x), str(x))
        )

    # --- FORMATOWANIE WIERSZY DETALI (2. seria) ---
    # Czyścimy pola, które mają pozostać puste (;;;)
    df_export.loc[is_detail_row, ["Miejsce", "Drużyna", "Kraj", "Suma"]] = ""

    # 4. Finalne przygotowanie kolumn
    df_export = df_export.rename(columns={"Miejsce": "Lp."})
    
    # Wybieramy kolumny w Twojej kolejności
    final_cols = ["Lp.", "Drużyna", "Kraj", "Jumper1", "Jumper2", "Jumper3", "Jumper4", "Suma"]
    
    # Filtrujemy tylko istniejące kolumny, by uniknąć błędów
    available_cols = [c for c in final_cols if c in df_export.columns]
    df_final = df_export[available_cols]

    # 5. Logika ścieżki zapisu
    safe_code = "".join((ch if ch.isalnum() or ch in "._-" else "_") for ch in code)
    
    # Specjalne foldery dla kwalifikacji CC/MSC
    if code.startswith(("Q_CC_", "Q_MSC_")):
        root = Path(season) / f"Team {season}"
    else:
        root = Path(season) / f"Mistrzostwa {season}"

    filename = f"{season}_{safe_code}.csv"

    # 6. Zapis do pliku
    try:
        root.mkdir(parents=True, exist_ok=True)
        path = root / filename
        
        # UTF-8-SIG zapewnia poprawne polskie znaki w Excelu
        df_final.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
        
        messagebox.showinfo(
            "Mistrzostwa – TEAM", 
            f"Zapisano pełną klasyfikację do:\n{path}"
        )
    except Exception as e:
        messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać pliku:\n{e}")

# --------------- LOADER ROSTERU ---------------
def load_roster_custom(excel_path: Path, sheet_name: str) -> pd.DataFrame:
    records = []
    current_country = None
    raw_df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
    for _, row in raw_df.iterrows():
        name_or_country = str(row[0]).strip() if not pd.isna(row[0]) else None
        um = row[2]
        forma = row[3]
        if name_or_country and (pd.isna(um) and pd.isna(forma)):
            current_country = name_or_country
        elif name_or_country and current_country and not pd.isna(um) and not pd.isna(forma):
            if len(name_or_country) >= 3:
                records.append({"Kraj": current_country, "Zawodnik": name_or_country, "UM": um, "Forma": forma})
    return pd.DataFrame(records)

# ----------------- ROZSZERZONA SYMULACJA -----------------
def simulate_team_competition_ext(
    roster: pd.DataFrame,
    K: int = 125,
    HS: int = 140,
    meter_value: float | None = None,
    wind_ms_mean: float = 0.0,
    wind_ms_sd: float = 0.8,
    gate_base: int = 10,
    gate_points_per_step: float = 4.0,
    p_gate_change: float = 0.06,
    max_gate_delta: int = 2,
    rng: np.random.Generator | None = None,
    randomness: float = 1.5,
    elite_regress: float = 1.0,
    wind_phi: float = 0.75,
    wind_takeoff_gain: float = 0.5,
    wind_flight_gain: float = 2.2,
    judges_rho: float = 0.55,
    finalists_n: int = 8,
    num_series: int = 2,
    max_sigma: float | None = None,
    style_fall_penalty: float | None = None,
    fall_base: float | None = None,
    fall_distance_gain: float | None = None,
):
    if meter_value is None:
        meter_value = compute_meter_value(K)

    rng_loc = rng or np.random.default_rng()

    teams = []
    for kraj, group in roster.groupby("Kraj"):
        if kraj == "N/A" or pd.isna(kraj):
            continue
        if len(group) >= 4:
            top4 = group.sort_values("UM", ascending=False).head(4)
            teams.append((kraj, top4))

    if not teams:
        return None, None, None, None

    def one_round(members, seria):
        extra = {
            "randomness": randomness,
            "elite_regress": elite_regress,
            "wind_phi": wind_phi,
            "wind_takeoff_gain": wind_takeoff_gain,
            "wind_flight_gain": wind_flight_gain,
            "judges_rho": judges_rho,
            "max_sigma": max_sigma,
            "style_fall_penalty": style_fall_penalty,
            "fall_base": fall_base,
            "fall_distance_gain": fall_distance_gain,
        }
        extra = filter_kwargs_for(simulate_round, extra)

        r = simulate_round(
            members, K, HS, meter_value,
            wind_ms_mean, wind_ms_sd,
            gate_base, gate_points_per_step,
            p_gate_change, max_gate_delta, rng_loc,
            **extra
        )
        r = normalize_round_df(r, K, meter_value)
        r["Seria"] = seria
        return r

    # SERIA 1
    team_scores_1, detailed_1 = [], []
    for kraj, members in teams:
        r1 = one_round(members, 1)
        tp = r1["Punkty rundy"].sum()
        team_scores_1.append((kraj, tp))
        detailed_1.append(r1.assign(Druzyna=kraj))

    df_r1 = pd.concat(detailed_1, ignore_index=True)
    team_scores_1 = pd.DataFrame(team_scores_1, columns=["Druzyna", "Punkty1"]).sort_values("Punkty1", ascending=False)

    # Finaliści
    finalists = set(team_scores_1.head(max(1, int(finalists_n)))["Druzyna"])

    # SERIA 2 (opcjonalnie)
    df_r2 = pd.DataFrame()
    team_scores_2 = pd.DataFrame(columns=["Druzyna","Punkty2"])
    if num_series >= 2:
        team_scores_2_list, detailed_2 = [], []
        for kraj, members in teams:
            if kraj not in finalists:
                continue
            r2 = one_round(members, 2)
            tp = r2["Punkty rundy"].sum()
            team_scores_2_list.append((kraj, tp))
            detailed_2.append(r2.assign(Druzyna=kraj))
        if detailed_2:
            df_r2 = pd.concat(detailed_2, ignore_index=True)
            team_scores_2 = pd.DataFrame(team_scores_2_list, columns=["Druzyna", "Punkty2"])

    # Zsumowana klasyfikacja
    klasyf = team_scores_1.merge(team_scores_2, on="Druzyna", how="left")

    # wypełnij tylko liczby, nie dotykaj kolumn tekstowych (żeby nie triggerować downcastu)
    num_cols = klasyf.select_dtypes(include=["number"]).columns
    if len(num_cols):
        klasyf[num_cols] = klasyf[num_cols].fillna(0.0)

    klasyf["Punkty"] = klasyf["Punkty1"] + klasyf["Punkty2"]
    klasyf = klasyf.sort_values("Punkty", ascending=False).reset_index(drop=True)
    klasyf.insert(0, "Miejsce", range(1, len(klasyf)+1))

    fis_scale_team = [400, 350, 300, 250, 200, 150, 100, 50]

    if "Miejsce" in klasyf.columns:
        # zabezpieczenie na NaN/tekst
        _m = pd.to_numeric(klasyf["Miejsce"], errors="coerce").fillna(0).astype(int)
        klasyf["Punkty FIS"] = _m.map(lambda x: fis_scale_team[x-1] if 1 <= x <= len(fis_scale_team) else 0)
    else:
        klasyf["Punkty FIS"] = 0

    all_rounds = pd.concat([df_r1, df_r2], ignore_index=True) if not df_r2.empty else df_r1
    return df_r1, df_r2, klasyf, all_rounds

from team_results_export import export_team_results_xlsx

def save_to_excel_custom(
    dfr1_show, dfr2_show, klasyf, two_rows, falls_df,
    hill_name, outdir, pattern, one_series: bool
):
    extra = {
        "Klasyfikacja 2-wiersze": two_rows,
        "Upadki": falls_df
    }

    # wszystko zapisuje excel_saver z ładnym formatowaniem i stylami
    saved = export_team_results_xlsx(
        out_dir=outdir,
        filename_pattern=pattern,
        hill_name=hill_name,
        kval_df=dfr1_show,
        contest_rows=dfr2_show,
        klasyf_df=klasyf,
        extra_sheets=extra
    )
    return saved

# === TEAM: Country selector and roster helper ===
class CountrySelectFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        install_global_combobox_wheel(self.winfo_toplevel())
        install_combobox_scroll_everywhere(self.winfo_toplevel())
        self.columnconfigure(0, weight=3)  # dostępne kraje
        self.columnconfigure(1, weight=0)  # przyciski
        self.columnconfigure(2, weight=3)  # wybrane kraje
        self.columnconfigure(3, weight=4)  # podgląd składów
        self.rowconfigure(1, weight=1)

        # LEWA TABELA (zostaje jak masz):
        left_wrap, self.tree_all = add_country_table_with_flags(self, height=26)
        left_wrap.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self._flag_imgs = {}
        # PRAWA TABELA: Reprezentacja (flaga + pełna nazwa) + Kraj (kod)
        right_wrap, self.tree_sel = add_country_table_with_flags(self, height=26)
        right_wrap.grid(row=1, column=2, sticky="nsew", padx=(6, 0))

        # --- TUNING SZEROKOŚCI, żeby wagi 60/40 działały realnie ---

        # LEWA tabela: zmniejsz minimum
        try:
            self.tree_all.column("#0", width=210, minwidth=120, stretch=True)
            self.tree_all.column("Kraj", width=60, minwidth=50, stretch=False)
        except Exception:
            pass

        # PRAWA tabela: zmniejsz minimum
        try:
            self.tree_sel.column("#0", width=210, minwidth=120, stretch=True)
            self.tree_sel.column("Kraj", width=60, minwidth=50, stretch=False)
        except Exception:
            pass

        # PREVIEW: mniejsza baza + brak wymuszania szerokości
        try:
            self.tree_preview.column("#0", width=55, minwidth=45, stretch=False)
            self.tree_preview.column("Zawodnik", width=160, minwidth=120, stretch=True)
            self.tree_preview.column("UM", width=50, minwidth=40, stretch=False)
            self.tree_preview.column("Forma", width=55, minwidth=40, stretch=False)
        except Exception:
            pass


        # referencje do obrazków po prawej (na wszelki wypadek oddzielnie)
        self._flag_imgs_right = []
        self.tree_all.bind("<Double-1>", lambda e: self._add_one())
        self.tree_sel.bind("<Double-1>", lambda e: self._rem_one())

        btns = ttk.Frame(self); btns.grid(row=1, column=1, padx=3, pady=0)
        ttk.Button(btns, text=">>", command=self._add).pack(pady=(40,6))
        ttk.Button(btns, text=">",  command=self._add_one).pack(pady=6)
        ttk.Button(btns, text="<",  command=self._rem_one).pack(pady=6)
        ttk.Button(btns, text="<<", command=self._clear).pack(pady=6)

        ttk.Separator(btns, orient="horizontal").pack(fill="x", pady=(12, 8))

        ttk.Button(btns, text="WC-M", command=lambda: self._btn_top_from_classif("WC-M", 11)).pack(fill="x", pady=2)
        ttk.Button(btns, text="WC-W", command=lambda: self._btn_top_from_classif("WC-W", 11)).pack(fill="x", pady=2)
        ttk.Button(btns, text="GP-M", command=lambda: self._btn_top_from_classif("GP-M", 12)).pack(fill="x", pady=(8,2))
        ttk.Button(btns, text="GP-W", command=lambda: self._btn_top_from_classif("GP-W", 12)).pack(fill="x", pady=2)
        ttk.Button(btns, text="GP-MIX", command=self._btn_gp_mix).pack(fill="x", pady=(8,2))
        ttk.Button(btns, text="CC - Q", command=self._btn_cc).pack(fill="x", pady=(8,2))
        ttk.Button(btns, text="CC - Groups", command=self._btn_cc_groups).pack(fill="x", pady=2)
        ttk.Button(btns, text="MSC - Men", command=self._btn_msc_men)\
            .pack(fill="x", pady=(8,2))
        ttk.Button(btns, text="MSC - Women", command=self._btn_msc_women)\
            .pack(fill="x", pady=2)

        ttk.Separator(btns, orient="horizontal").pack(fill="x", pady=(12, 8))
        ttk.Label(btns, text="Kontynent:", font=("TkDefaultFont", 8)).pack()
        self._continent_var = tk.StringVar(value="Europe")
        _cont_map = {
            "Europa":      "Europe",
            "Azja":        "Asia",
            "N. Ameryka":  "North America",
            "S. Ameryka":  "South America",
            "Oceania":     "Oceania",
            "Afryka":      "Africa",
        }
        self._cont_map = _cont_map
        ttk.Combobox(
            btns,
            textvariable=self._continent_var,
            values=list(_cont_map.keys()),
            state="readonly",
            width=11,
        ).pack(fill="x", pady=(0, 4))
        ttk.Button(
            btns,
            text="Dodaj kontynent",
            command=lambda: self._btn_continent(
                self._cont_map.get(self._continent_var.get(), self._continent_var.get())
            )
        ).pack(fill="x", pady=2)

        bar = ttk.Frame(self); bar.grid(row=2, column=0, columnspan=4, sticky="ew", padx=6, pady=(0,6))
        bar.columnconfigure(0, weight=1)
        self.sex_var = tk.StringVar(value="")  # domyślnie wszystkie
        ttk.Label(bar, text="Płeć:").pack(side="left")
        ttk.Combobox(bar, textvariable=self.sex_var, values=["","M","W","MIX"], width=6, state="readonly").pack(side="left", padx=(4,10))
        self.exclude_injuries = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Wyklucz kontuzjowanych (Kontuzja != 0)", variable=self.exclude_injuries).pack(side="left")

        # --- NOWE: użyj filtrów z widoku bazy zawodników przy budowie rosteru ---
        self.use_db_filters = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar,
            text="Użyj filtrów z Bazy zawodników dla wyboru składu",
            variable=self.use_db_filters
        ).pack(side="left", padx=(12,0))

        self.season_var = tk.StringVar(value="S45")
        ttk.Label(bar, text="Sezon:").pack(side="left", padx=(14,2))
        ttk.Entry(bar, textvariable=self.season_var, width=5).pack(side="left")

        self.info = ttk.Label(bar, text="", foreground="#666")
        self.info.pack(side="right")
        # BEZPOŚREDNIO DO METODY, A NIE LAMBDA WYWOLUJĄCA NIEISTNIEJĄCĄ FUNKCJĘ
        ttk.Button(bar, text="Odśwież kraje", command=self._btn_refresh).pack(side="right", padx=(0,8))

        # ===== TRZECIA TABELA: PODGLĄD SKŁADÓW OBOK =====
        prev_wrap = ttk.Labelframe(self, text="Składy (zawodnicy do skoku)")
        prev_wrap.grid(row=1, column=3, sticky="nsew", padx=(6, 0))
        prev_wrap.columnconfigure(0, weight=1)
        prev_wrap.rowconfigure(0, weight=1)

        self.tree_preview = ttk.Treeview(
            prev_wrap,
            columns=("Zawodnik", "UM", "Forma"),
            show="tree headings",
            height=26
        )
        self.tree_preview.grid(row=0, column=0, sticky="nsew")

        vsb_prev = ttk.Scrollbar(prev_wrap, orient="vertical", command=self.tree_preview.yview)
        vsb_prev.grid(row=0, column=1, sticky="ns")
        self.tree_preview.configure(yscrollcommand=vsb_prev.set)

        self.tree_preview.heading("#0", text="Kraj")
        self.tree_preview.column("#0", width=70, stretch=False, anchor="w")
        for c, w in [("Zawodnik", 220), ("UM", 60), ("Forma", 70)]:
            self.tree_preview.heading(c, text=c)
            self.tree_preview.column(c, width=w, stretch=(c == "Zawodnik"), anchor="center")

        # odświeżaj podgląd gdy zmienia się wybór / filtry
        try:
            self.tree_sel.bind("<<TreeviewSelect>>", lambda e: self._refresh_roster_preview())
        except Exception:
            pass

        try:
            self.sex_var.trace_add("write", lambda *_: self._on_filter_change())
            self.exclude_injuries.trace_add("write", lambda *_: self._on_filter_change())
        except Exception:
            pass

    # --- przyciski list prawo/lewo ---
    def _add(self):
        """Przerzuć wszystkie z LEWEJ do PRAWEJ."""
        codes = [self.tree_all.set(iid, "Kraj") for iid in self.tree_all.get_children("")]
        self._set_right(codes)

    def _add_one(self):
        """Przerzuć zaznaczone z LEWEJ do PRAWEJ."""
        sel_iids = self.tree_all.selection()
        codes = [self.tree_all.set(iid, "Kraj") for iid in sel_iids]
        self._add_right(codes)

    def _rem_one(self):
        """Usuń zaznaczone z PRAWEJ."""
        for iid in list(self.tree_sel.selection()):
            self.tree_sel.delete(iid)
        self._update_counter()

    def _clear(self):
        """Wyczyść PRAWĄ tabelę."""
        for iid in self.tree_sel.get_children(""):
            self.tree_sel.delete(iid)
        self._update_counter()

    def _btn_top_from_classif(self, key: str, top_n: int):
        """Handler dla WC-M/WC-W/GP-M/GP-W."""
        try:
            codes = self._load_top_nations_from_csv(key, top_n)
            if not codes:
                return
            # nadpisz prawą listę TOPami
            self._set_right(codes)
        except Exception as e:
            try:
                messagebox.showerror("Klasyfikacje", str(e))
            except Exception:
                pass

    def _load_top_nations_from_csv(self, key: str, top_n: int) -> list[str]:
        """
        Wczytuje TOP N krajów z pliku:
        ./SEZON/Klasyfikacje SEZON/SEZON_{key}__nations.csv
        gdzie key np. 'WC-M', 'GP-W'.
        """
        import pandas as pd
        from pathlib import Path

        # sezon z comboboxa; fallback na S45
        season_var = getattr(self, "season_var", None)
        season = season_var.get().strip() if season_var is not None else "S45"
        if not season:
            season = "S45"

        cls_dir = Path(f"./{season}/Klasyfikacje {season}")
        cls_dir.mkdir(parents=True, exist_ok=True)
        nations_path = cls_dir / f"{season}_{key}__nations.csv"

        if not nations_path.exists():
            raise RuntimeError(f"Nie znaleziono pliku klasyfikacji:\n{nations_path}")

        # wczytanie z autodetekcją separatora / kodowania
        last_err = None
        df = None
        for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
            try:
                df = pd.read_csv(nations_path, sep=None, engine="python", encoding=enc)
                break
            except Exception as e:
                last_err = e
                df = None

        if df is None:
            try:
                df = pd.read_csv(nations_path, sep=";", encoding="utf-8-sig")
            except Exception:
                raise RuntimeError(f"Nie mogę wczytać CSV:\n{nations_path}\n{last_err}")

        # wykryj kolumnę z kodem kraju
        nat_col = None
        for c in df.columns:
            if str(c).strip().upper() in ("NAT", "KRAJ", "NATIONCODE"):
                nat_col = c
                break
        if nat_col is None:
            nat_col = next((c for c in df.columns if "NAT" in str(c).upper()), None)

        if nat_col is None:
            raise RuntimeError(
                f"Plik nie ma kolumny NAT/Kraj:\n{nations_path}\nNagłówki: {list(df.columns)}"
            )

        codes = (
            df[nat_col]
            .astype(str)
            .str.upper()
            .str.strip()
        )
        codes = [c for c in codes.tolist() if c and c != "NAN"]

        return codes[:int(top_n)]

    def _btn_cc(self):
        """
        CC: przenosi tylko kraje, które mają min. 4 zdrowych MEN i 4 zdrowe WOMEN.
        Działa na liście krajów (lewa → prawa).
        """
        eligible = _countries_with_min_healthy_mw(min_m=4, min_w=4)
        if not eligible:
            messagebox.showinfo(
                "CC",
                "Brak krajów z min. 4 zdrowymi MEN i 4 zdrowymi WOMEN w bazie zawodników."
            )
            return

        # poprawne drzewka
        tv_src = self.tree_all
        tv_dst = self.tree_sel

        moved = 0
        for iid in list(tv_src.get_children("")):
            nat = str(tv_src.set(iid, "Kraj")).strip().upper()
            if nat in eligible:
                item = tv_src.item(iid)
                text = item.get("text", "")
                vals = item.get("values", ())

                # obrazek z istniejącego wiersza lub z cache flag
                img = item.get("image", "")
                if not img:
                    img = _flag_cached(nat)

                if img:
                    self._flag_imgs_right.append(img)

                tv_dst.insert("", "end", text=text, image=img, values=vals)

                tv_src.delete(iid)
                moved += 1

        self._update_counter()

        if moved == 0:
            messagebox.showinfo(
                "CC",
                "Żaden z krajów na liście nie spełnia warunku 4 zdrowych MEN + 4 zdrowe WOMEN."
            )

    def _btn_cc_groups(self):
        """
        CC - Groups:
        • czyta kwalifikacje CC (S45_Q_CC_M/W/X.csv) z folderu {Sezon}/Team {Sezon}
        • sumuje MEN/WOMEN/MIX → Suma
        • bierze TOP16 po Suma
        • przenosi kraje z tej szesnastki z lewej tabeli do prawej
        """
        from pathlib import Path

        # sezon z dolnego paska ("Sezon:" w zakładce Kraje)
        season = (self.season_var.get() or "").strip() or "S45"
        dir_path = Path(season) / f"Team {season}"

        if not dir_path.is_dir():
            messagebox.showerror(
                "CC - Groups",
                f"Folder z kwalifikacjami CC nie istnieje:\n{dir_path}"
            )
            return

        try:
            df_q = _cc_q_summary_from_dir(dir_path)
        except Exception as e:
            messagebox.showerror(
                "CC - Groups",
                f"Problem z wczytaniem kwalifikacji CC:\n{e}"
            )
            return

        if df_q is None or df_q.empty:
            messagebox.showinfo(
                "CC - Groups",
                f"Nie znaleziono żadnych danych kwalifikacji CC w:\n{dir_path}"
            )
            return

        # upewniamy się, że mamy kolumny "Kraj" i "Suma"
        if "Kraj" not in df_q.columns or "Suma" not in df_q.columns:
            messagebox.showerror(
                "CC - Groups",
                "Tabela kwalifikacji CC nie ma kolumn 'Kraj' i 'Suma'."
            )
            return

        # sortowanie po Suma (powinno już być, ale nie ufamy nikomu, nawet sobie)
        df_q = df_q.sort_values("Suma", ascending=False, kind="stable").reset_index(drop=True)

        if len(df_q) < 16:
            messagebox.showinfo(
                "CC - Groups",
                f"Za mało drużyn w kwalifikacjach CC (mam {len(df_q)}, potrzebuję co najmniej 16)."
            )
            return

        top16 = df_q.head(16)
        nat_set = {
            str(row["Kraj"]).strip().upper()
            for _, row in top16.iterrows()
            if str(row.get("Kraj", "")).strip()
        }

        if not nat_set:
            messagebox.showinfo(
                "CC - Groups",
                "Nie udało się wyciągnąć kodów krajów z TOP16 kwalifikacji CC."
            )
            return

        tv_src = self.tree_all
        tv_dst = self.tree_sel

        moved = 0
        for iid in list(tv_src.get_children("")):
            nat = str(tv_src.set(iid, "Kraj")).strip().upper()
            if nat in nat_set:
                item = tv_src.item(iid)
                text = item.get("text", "")
                vals = item.get("values", ())

                img = item.get("image", "")
                if not img:
                    img = _flag_cached(nat)
                if img:
                    self._flag_imgs_right.append(img)

                tv_dst.insert("", "end", text=text, image=img, values=vals)
                tv_src.delete(iid)
                moved += 1

        self._update_counter()

        if moved == 0:
            messagebox.showinfo(
                "CC - Groups",
                "Żaden z krajów na liście po lewej nie jest w TOP16 kwalifikacji CC."
            )

    def _btn_gp_mix(self):
        """GP-MIX = TOP12 z GP-M + dopisane unikalne z GP-W."""
        try:
            m = self._load_top_nations_from_csv("GP-M", 12)
            w = self._load_top_nations_from_csv("GP-W", 12)

            mix = []
            seen = set()

            # najpierw TOP12 z GP-M
            for c in m:
                if c and c not in seen:
                    seen.add(c)
                    mix.append(c)

            # dopisz te z GP-W których nie było w GP-M
            for c in w:
                if c and c not in seen:
                    seen.add(c)
                    mix.append(c)

            if mix:
                self._set_right(mix)

        except Exception as e:
            try:
                messagebox.showerror("Klasyfikacje", str(e))
            except Exception:
                pass

    def _btn_msc(self, sex: str):
        """
        MSC - Men/Women: przenieś do PRAWEJ TOP16 krajów
        z kwalifikacji MSC (Q) dla danej płci.
        Czyta {season}/Team {season}/{season}_Q_MSC_M/W.csv
        przez _msc_q_summary_from_dir.
        """
        from pathlib import Path
        import pandas as pd
        from tkinter import messagebox

        # sezon tak jak w reszcie zakładki 'Kraje'
        season = (self.season_var.get() or "").strip() or "S45"
        dir_path = Path(season) / f"Team {season}"

        try:
            df_q = _msc_q_summary_from_dir(dir_path, sex=sex)
        except Exception as e:
            print(f"[MSC-Q] Brak pliku kwalifikacji ({sex}): {e}")
            return

        if df_q is None or getattr(df_q, "empty", True):
            messagebox.showinfo("MSC – Q", "Brak danych kwalifikacji MSC.")
            return

        df_q = df_q.copy()
        # standardowo sortujemy po 'Suma' – dokładnie tak jak w MSC
        if "Suma" in df_q.columns:
            df_q = df_q.sort_values("Suma", ascending=False, kind="stable")
        df_q = df_q.reset_index(drop=True)

        if len(df_q) < 16:
            messagebox.showinfo(
                "MSC – Q",
                f"Za mało drużyn w kwalifikacjach MSC (mam {len(df_q)}, "
                f"potrzebuję co najmniej 16)."
            )
            return

        top16 = df_q.head(16)
        nat_set = {
            str(row.get("Kraj", "")).strip().upper()
            for _, row in top16.iterrows()
            if str(row.get("Kraj", "")).strip()
        }

        if not nat_set:
            messagebox.showinfo(
                "MSC – Q",
                "Nie udało się wyciągnąć kodów krajów z TOP16 kwalifikacji MSC."
            )
            return

        tv_src = self.tree_all
        tv_dst = self.tree_sel
        moved = 0

        # kopiujemy dokładnie mechanikę z _btn_cc_groups
        for iid in list(tv_src.get_children("")):
            nat = str(tv_src.set(iid, "Kraj")).strip().upper()
            if nat in nat_set:
                item = tv_src.item(iid)
                text = item.get("text", "")
                vals = item.get("values", ())

                img = item.get("image", "")
                if not img:
                    img = _flag_cached(nat)
                if img:
                    self._flag_imgs_right.append(img)

                tv_dst.insert("", "end", text=text, image=img, values=vals)
                tv_src.delete(iid)
                moved += 1

        self._update_counter()

        if moved == 0:
            messagebox.showinfo(
                "MSC – Q",
                "Żaden z krajów na liście po lewej nie jest w TOP16 kwalifikacji MSC."
            )

    def _btn_msc_men(self):
        self._btn_msc("M")

    def _btn_msc_women(self):
        self._btn_msc("W")

    def _btn_continent(self, continent: str):
        """
        Przenosi z LEWEJ na PRAWĄ wszystkie kraje należące do danego kontynentu.
        Dane kontynentów wczytuje z ALL_NATIONS_CONTINENTS.csv (szuka w standardowych lokalizacjach).
        """
        import pandas as pd
        from tkinter import messagebox

        # Wyszukaj plik CSV z kontynentami
        cont_path = _find_nearby_file(
            "ALL_NATIONS_CONTINENTS.csv",
            alt_patterns=["*NATIONS*CONTINENTS*.csv", "*continents*.csv"],
        )
        if not cont_path:
            messagebox.showerror(
                "Kontynenty",
                "Nie znaleziono pliku ALL_NATIONS_CONTINENTS.csv.\n"
                "Umieść go w tym samym folderze co program."
            )
            return

        # Wczytaj plik z detekcją separatora i kodowania
        df_cont = None
        for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
            try:
                df_cont = pd.read_csv(cont_path, sep=None, engine="python", encoding=enc)
                break
            except Exception:
                df_cont = None

        if df_cont is None or df_cont.empty:
            messagebox.showerror("Kontynenty", f"Nie mogę wczytać pliku:\n{cont_path}")
            return

        # Kolumna z kodem kraju (Kraj) i kontynentem (Continent)
        nat_col = next(
            (c for c in df_cont.columns if str(c).strip().upper() in ("KRAJ", "NAT", "CODE", "KOD")),
            None
        )
        cont_col = next(
            (c for c in df_cont.columns if "CONTINENT" in str(c).strip().upper()),
            None
        )

        if not nat_col or not cont_col:
            messagebox.showerror(
                "Kontynenty",
                f"Plik nie ma wymaganych kolumn (Kraj, Continent).\nMam: {list(df_cont.columns)}"
            )
            return

        # Zbuduj zbiór kodów krajów dla danego kontynentu
        mask = df_cont[cont_col].astype(str).str.strip() == continent
        eligible = set(
            df_cont.loc[mask, nat_col].astype(str).str.strip().str.upper().tolist()
        )

        if not eligible:
            messagebox.showinfo("Kontynenty", f"Brak krajów przypisanych do: {continent}")
            return

        tv_src = self.tree_all
        tv_dst = self.tree_sel
        moved = 0

        for iid in list(tv_src.get_children("")):
            nat = str(tv_src.set(iid, "Kraj")).strip().upper()
            if nat in eligible:
                item = tv_src.item(iid)
                text = item.get("text", "")
                vals = item.get("values", ())

                img = item.get("image", "")
                if not img:
                    img = _flag_cached(nat)
                if img:
                    self._flag_imgs_right.append(img)

                tv_dst.insert("", "end", text=text, image=img, values=vals)
                tv_src.delete(iid)
                moved += 1

        self._update_counter()

        if moved == 0:
            messagebox.showinfo(
                "Kontynenty",
                f"Żaden z krajów na liście po lewej nie należy do: {continent}"
            )

    def _add_right(self, codes: list[str]):
        """Dopisz do PRAWEJ brakujące kody (z flagą)."""
        have = self._right_codes_set()
        new_codes = [c for c in codes if (c or "").strip().upper() not in have]
        for code, full in self._pairs_from_codes(new_codes):
            img = _flag_cached(code)
            self._flag_imgs_right.append(img)
            self.tree_sel.insert("", "end", text=" " + full, image=img, values=(code,))
        self._update_counter()

    def _set_right(self, codes: list[str]):
        self._populate_right_pairs(self._pairs_from_codes(codes))

    def _right_codes_set(self) -> set[str]:
        return {self.tree_sel.set(iid, "Kraj") for iid in self.tree_sel.get_children("")}

    def _pairs_from_codes(self, codes: list[str]) -> list[tuple[str, str]]:
        out = []
        for c in codes:
            code = (c or "").strip().upper()
            if code:
                out.append((code, TEAM_NAME.get(code, code)))
        return out

    def _populate_right_pairs(self, pairs: list[tuple[str, str]]):
        for iid in self.tree_sel.get_children(""):
            self.tree_sel.delete(iid)
        self._flag_imgs_right.clear()
        for code, full in sorted(pairs, key=lambda x: x[1].lower()):
            img = _flag_cached(code)
            self._flag_imgs_right.append(img)
            self.tree_sel.insert("", "end", text=" " + full, image=img, values=(code,))
        self._update_counter()

    def set_available_countries(self, countries):
        """Wypełnij LEWĄ tabelę (flaga + pełna nazwa + kod). NIE ruszaj prawej."""
        # zapamiętaj zaznaczenie po LEWEJ
        prev_sel_codes = {self.tree_all.set(iid, "Kraj") for iid in self.tree_all.selection()}

        # wyczyść lewą
        for iid in self.tree_all.get_children(""):
            self.tree_all.delete(iid)
        self._flag_imgs.clear()

        # unikalne kody, posortowane po nazwie
        uniq = sorted({str(x).upper().strip() for x in countries if str(x).strip()},
                    key=lambda c: (TEAM_NAME.get(c, c)).lower())

        # wstaw wiersze: tekst idzie do #0 (kolumna drzewa), kod do "Kraj"
        for code in uniq:
            img = _flag_cached(code)
            self._flag_imgs[code] = img
            full = TEAM_NAME.get(code, code)
            self.tree_all.insert("", "end", text=" " + full, image=img, values=(code,))

        # odtwórz zaznaczenie
        if prev_sel_codes:
            for iid in self.tree_all.get_children(""):
                if self.tree_all.set(iid, "Kraj") in prev_sel_codes:
                    self.tree_all.selection_add(iid)

        self._update_counter()

    def _update_counter(self):
        left_n = len(self.tree_all.get_children(""))
        right_n = len(self.tree_sel.get_children(""))
        self.info.configure(text=f"Dostępne: {left_n} | Wybrane: {right_n}")
        
        try:
            self._refresh_roster_preview()
        except Exception:
            pass


    def get_selected(self) -> list[str]:
        """Zwraca kody z PRAWEJ (to leci do symulacji)."""
        return [self.tree_sel.set(iid, "Kraj") for iid in self.tree_sel.get_children("")]

    # --- PRZYCISK: bezpieczne wywołanie odświeżenia ---
    def _btn_refresh(self):
        db = getattr(self, "_db_ref", None)
        if db is not None:
            self.refresh_countries(db)

    # --- TE DWIE METODY SĄ KLUCZOWE I MUSZĄ ISTNIEĆ ---
    def populate_from_db(self, db_frame: "PlayerDBFrame"):
        import pandas as _pd
        df = _db_live_dataframe(db_frame)  # patrz helper niżej
        try:
            print("[KRAJE] rows:", getattr(df, "shape", ["?","?"])[0], "cols:", list(df.columns) if hasattr(df,"columns") else [])
        except Exception:
            pass

        if df is None or len(getattr(df, "index", [])) == 0:
            self.set_available_countries([])
            return
        
        # --- NOWE: filtry z zakładki "Kraje" wpływają na listę dostępnych krajów ---
        df = df.copy()

        # normalizacja płci (jeśli jest)
        if "Płeć" in df.columns:
            df["Płeć"] = df["Płeć"].astype(str).str.upper().str[:1]

        sex = (self.sex_var.get() or "").strip().upper()
        if sex in ("M", "W") and "Płeć" in df.columns:
            df = df[df["Płeć"] == sex]

        # kontuzje: jeśli zaznaczone "wyklucz kontuzjowanych"
        if getattr(self, "exclude_injuries", None) is not None and self.exclude_injuries.get():
            if "Kontuzja" in df.columns:
                kont = _pd.to_numeric(df["Kontuzja"], errors="coerce").fillna(0)
                df = df[kont == 0]

        def _norm(s): return str(s).strip().replace("\xa0"," ").lower()
        col_map = {c: _norm(c) for c in getattr(df, "columns", [])}
        kraj_col = None
        for original, norm in col_map.items():
            if norm == "kraj":
                kraj_col = original; break
        if kraj_col is None:
            for original, norm in col_map.items():
                if norm in ("nation","nat","country"):
                    kraj_col = original; break
        if kraj_col is None:
            self.set_available_countries([])
            return

        ser = df[kraj_col].astype(str).str.upper().str.strip()
        ser = ser[(ser.str.len() > 0) & (ser != "NAN")]

        # --- NOWE: tylko kraje z min. 4 zawodnikami po filtrach ---
        counts = ser.value_counts()
        ok_nats = set(counts[counts >= 4].index.tolist())

        countries = sorted(ok_nats)
        self.set_available_countries(countries)


    def _countries_source_pairs(self):
        """
        Zbiera pary (kod, pełna_nazwa). Najpierw z rosteru,
        nazwy przez TEAM_NAME, fallback na kod gdy brak mapy.
        """
        try:
            df = getattr(self, "_db_df_full", None)
            if df is None:
                # spróbuj wziąć z PlayerDBFrame
                db = getattr(self, "_db_ref", None)
                if db is not None and hasattr(db, "_full_df"):
                    df = db._full_df
            if df is None or df.empty:
                return []
            nat = (df["Kraj"].astype(str).str.upper().str.strip()
                if "Kraj" in df.columns else pd.Series([], dtype=str))
            unique = sorted(set([c for c in nat if c]))
            pairs = [(c, TEAM_NAME.get(c, c)) for c in unique]
            return pairs
        except Exception:
            return []

    def refresh_countries(self, db_frame=None, *_):
        """
        Odśwież lewą listę krajów na podstawie AKTUALNEGO widoku bazy
        + filtrów z tej zakładki (płeć / kontuzje).
        """
        if db_frame is None:
            db_frame = getattr(self, "_db_ref", None)

        if db_frame is not None:
            self.populate_from_db(db_frame)
            return

        # fallback (gdyby baza nie była podpięta)
        pairs = self._countries_source_pairs()
        populate_country_rows_with_flags(self.tree_all, pairs)

        try:
            self._countries_count_lbl.config(
                text=f"Dostępne: {len(pairs)} | Wybrane: {len(getattr(self, '_selected_countries', []))}"
            )
        except Exception:
            pass

    def _on_filter_change(self):
        # zmiana filtra = odśwież kraje i podgląd składu
        try:
            self.refresh_countries()
        except Exception:
            pass
        self._refresh_roster_preview()

    def _refresh_roster_preview(self):
        """Wypisz pod każdą wybraną drużyną zawodników, którzy będą skakać."""
        tv = getattr(self, "tree_preview", None)
        if tv is None:
            return

        # wyczyść
        for iid in tv.get_children(""):
            tv.delete(iid)

        db_frame = getattr(self, "_db_ref", None)
        if db_frame is None:
            return

        try:
            roster = _roster_from_player_db_and_countries(db_frame, self)
        except Exception:
            roster = None

        if roster is None or getattr(roster, "empty", True):
            return

        # grupuj po kraju i wstaw jako drzewko
        try:
            roster["Kraj"] = roster["Kraj"].astype(str).str.upper().str.strip()
        except Exception:
            pass

        # trzymaj referencje do obrazków, żeby Tk ich nie zjadł przez GC
        self._preview_img_refs = []

        for kraj, grp in roster.groupby("Kraj", sort=False):
            kraj_code = str(kraj or "").strip().upper()
            img_kraj = _flag_cached(kraj_code)
            if img_kraj:
                self._preview_img_refs.append(img_kraj)

            # parent: kraj + flaga w #0
            parent = tv.insert(
                "", "end",
                text=f" {kraj_code}",
                image=img_kraj,
                values=("", "", "")
            )

            # dzieci: flaga (ta sama co kraj) + zawodnik w kolumnie "Zawodnik"
            for _, r in grp.iterrows():
                zawodnik = str(r.get("Zawodnik", "") or "")
                um = str(r.get("UM", "") or "")
                forma = str(r.get("Forma", "") or "")

                img_zaw = img_kraj  # ten sam kod kraju
                # (gdybyś kiedyś miał innych, tu możesz dać _flag_cached(r.get("Kraj")))
                if img_zaw:
                    self._preview_img_refs.append(img_zaw)

                tv.insert(
                    parent, "end",
                    text="",              # tekst pusty, bo nazwisko jest w kolumnie "Zawodnik"
                    image=img_zaw,        # flaga przy wierszu zawodnika
                    values=(zawodnik, um, forma)
                )

            tv.item(parent, open=True)


def _roster_from_player_db_and_countries(db_frame: "PlayerDBFrame", country_frame: "CountrySelectFrame"):
    import pandas as _pd

    # ZAWSZE bierz widok z bazy po filtrach
    df = _db_live_dataframe(db_frame)

    if df is None:
        df = _pd.DataFrame(columns=["Zawodnik","Kraj","UM","Forma","Płeć","Kontuzja","PrawoStartu","Wiek","JUN/SEN"])
    if df.empty:
        return _pd.DataFrame(columns=["Zawodnik","Kraj","UM","Forma"])

    df = df.copy()
    # normalize columns
    for c in ("UM","Forma","Kontuzja"):
        if c in df.columns:
            df[c] = _pd.to_numeric(df[c], errors="coerce").fillna(0)
    if "Kraj" in df.columns:
        df["Kraj"] = df["Kraj"].astype(str).str.upper().str.strip()
    if "Płeć" in df.columns:
        df["Płeć"] = df["Płeć"].astype(str).str.upper().str[:1]

    # filter by sex (optional)
    sex = (country_frame.sex_var.get() or "").strip().upper()
    if sex in ("M","W") and "Płeć" in df.columns:
        df = df[df["Płeć"] == sex]

    # filter injuries
    if getattr(country_frame, "exclude_injuries", None) is not None and "Kontuzja" in df.columns:
        if bool(country_frame.exclude_injuries.get()):
            df = df[_pd.to_numeric(df["Kontuzja"], errors="coerce").fillna(0) == 0]

    selected = country_frame.get_selected()
    if selected:
        df = df[df["Kraj"].isin(selected)]

    # ability score
    df["_ability_"] = 0.65 * _pd.to_numeric(df.get("UM", 0), errors="coerce").fillna(0) + 0.35 * _pd.to_numeric(df.get("Forma", 0), errors="coerce").fillna(0)

    # keep top 4 per country
    if "Kraj" in df.columns:
        if sex == "MIX" and "Płeć" in df.columns:
            # Dla każdego kraju: weź 2W + 2M wg ability i ustaw porządek W2, M2, W1, M1
            out_rows = []
            for kraj, grp in df.groupby("Kraj", as_index=False):
                w = grp[grp["Płeć"].astype(str).str.upper().eq("W")].sort_values("_ability_", ascending=False)
                m = grp[grp["Płeć"].astype(str).str.upper().eq("M")].sort_values("_ability_", ascending=False)
                if len(w) >= 2 and len(m) >= 2:
                    # W1/M1 = mocniejsi; W2/M2 = słabsi z TOP2
                    W1, W2 = w.head(2).iloc[0], w.head(2).iloc[1]
                    M1, M2 = m.head(2).iloc[0], m.head(2).iloc[1]
                    # przypisz OrderKey pod układ W2, M2, W1, M1
                    rows = []
                    for rec, ok in [(W2,1),(M2,2),(W1,3),(M1,4)]:
                        r = rec.to_dict()
                        r["OrderKey"] = ok
                        rows.append(r)
                    out_rows.extend(rows)
                else:
                    # brak 2W/2M – pomiń kraj w MIXED
                    continue
            df = _pd.DataFrame(out_rows) if out_rows else _pd.DataFrame(columns=df.columns.tolist() + ["OrderKey"])
        else:
            # tryb klasyczny: TOP4 wg ability
            df = (df.sort_values(["Kraj","_ability_"], ascending=[True, False])
                    .groupby("Kraj", as_index=False).head(4).copy())

    # porządki
    df.drop(columns=[c for c in ["_ability_"] if c in df.columns], inplace=True, errors="ignore")

    # minimalne kolumny – ale zatrzymaj też Płeć i OrderKey jeśli są (pomaga przy wyświetlaniu)
    keep = [c for c in ["Zawodnik","Kraj","UM","Forma","Płeć","OrderKey"] if c in df.columns]
    return df[keep].copy()

# === END TEAM helpers ===

# --- observers & utils ---
def _safe_db_dataframe(db_frame):
    import pandas as _pd
    # try common candidates
    for cand in ("_full_df", "_db_df"):
        df = getattr(db_frame, cand, None)
        if isinstance(df, _pd.DataFrame) and not df.empty:
            return df
    # try edit table
    try:
        tbl = getattr(db_frame, "_db_edit_table", None)
        if tbl is not None:
            df = tbl.dataframe()
            if isinstance(df, _pd.DataFrame) and not df.empty:
                return df
    except Exception:
        pass
    # try callable getter
    for name in ("get_dataframe", "get_df", "dataframe"):
        f = getattr(db_frame, name, None)
        if callable(f):
            try:
                df = f()
                if isinstance(df, _pd.DataFrame) and not df.empty:
                    return df
            except Exception:
                pass
    return _pd.DataFrame()

def _attach_db_refresh(db_frame, country_frame):
    """Odświeża flagi w Bazie zawodników i listę w zakładce Kraje."""
    setattr(country_frame, "_db_ref", db_frame)

    def _refresh_now(*_a, **_k):
        try:
            # 1. Odśwież listę krajów po lewej
            country_frame.refresh_countries(db_frame)
            
            # 2. Odśwież widok Bazy Zawodników o flagi
            df = _db_live_dataframe(db_frame)
            if df is not None and not df.empty:
                db_tv = db_frame._db_edit_table.tv_main
                db_cols = list(db_tv["columns"])
                # Używamy Twojego helpera do wypełnienia wierszy
                populate_player_rows_with_flags(
                    db_tv, df, 
                    name_col="Zawodnik", 
                    kraj_col="Kraj", 
                    cols_out=db_cols
                )
        except Exception as e:
            print(f"[DEBUG] Błąd odświeżania flag bazy: {e}")

    # Podpinamy odświeżanie pod metody ładujące
    for meth_name in ("_load_db_from_path", "_load_from_entry", "load_db", "open_file"):
        if hasattr(db_frame, meth_name):
            orig = getattr(db_frame, meth_name)
            if callable(orig):
                def wrapper_factory(fn):
                    def _w(*a, **k):
                        r = fn(*a, **k)
                        country_frame.after(100, _refresh_now)
                        return r
                    return _w
                setattr(db_frame, meth_name, wrapper_factory(orig))

    def _poll():
        try:
            df = _safe_db_dataframe(db_frame)
            # Sprawdzamy czy zmieniła się liczba wierszy lub kolumny
            key = (len(df), tuple(df.columns) if hasattr(df, "columns") else ())
            last = getattr(db_frame, "_last_poll_key", None)
            if key != last:
                db_frame._last_poll_key = key
                _refresh_now()
        except Exception:
            pass
        db_frame.after(1500, _poll)

    db_frame.after(1500, _poll)
    
def _db_live_dataframe(db_frame):
    """Zwróć DF dokładnie z widoku edytora, z fallbackami."""
    import pandas as _pd
    # 1) widok tabeli
    try:
        tbl = getattr(db_frame, "_db_edit_table", None)
        if tbl is not None:
            if hasattr(tbl, "dataframe") and callable(tbl.dataframe):
                df = tbl.dataframe()
                if isinstance(df, _pd.DataFrame) and not df.empty:
                    return df
            if hasattr(tbl, "model") and hasattr(tbl.model, "df"):
                df = tbl.model.df
                if isinstance(df, _pd.DataFrame) and not df.empty:
                    return df
    except Exception:
        pass
    # 2) bufory
    for cand in ("_full_df", "_db_df"):
        df = getattr(db_frame, cand, None)
        if isinstance(df, _pd.DataFrame) and not df.empty:
            return df
    # 3) gettery
    for name in ("get_dataframe", "get_df", "dataframe"):
        f = getattr(db_frame, name, None)
        if callable(f):
            try:
                df = f()
                if isinstance(df, _pd.DataFrame) and not df.empty:
                    return df
            except Exception:
                pass
    return _pd.DataFrame()

# === Embedded GUI builder ===
def build_gui(parent):
    tl = parent.winfo_toplevel()
    # ----------------------- GUI -----------------------
    root = parent
    tl.title("Symulator konkursu drużynowego — PRO+ (Parametry / Wyniki) — TEAM NAMES (fix)")

    try:
        tl.state("zoomed")
    except Exception:
        tl.attributes("-fullscreen", True)

    # używamy toplevela jako pseudo-„self”
    self = tl

    # --- AKTUALIZACJA BAZY ZAWODNIKÓW PO UPADKACH (TEAM) ---

    def _apply_injury_updates_to_db(event_name: str, week_val: int):
        import pandas as pd
        from tkinter import filedialog, messagebox

        falls_df = getattr(self, "_falls_last_df", None)
        falls_agg = getattr(self, "_falls_last_agg", None)

        # Bez ostatnich upadków nie ma co robić
        if not isinstance(falls_df, pd.DataFrame) or falls_df.empty:
            messagebox.showwarning(
                "Aktualizacja bazy",
                "Brak danych o upadkach z ostatniej symulacji.\n"
                "Najpierw uruchom konkurs TEAM z upadkami."
            )
            return

        # Zbuduj agregat, jeśli nie został zapisany
        if not isinstance(falls_agg, pd.DataFrame) or falls_agg.empty:
            cols = [c for c in [
                "Zawodnik", "Kraj",
                "Kontuzja (dni)",
                "ΔUM (kontuzja)",
                "ΔForma (kontuzja)",
            ] if c in falls_df.columns]
            if len(cols) < 3:
                messagebox.showwarning(
                    "Aktualizacja bazy",
                    "Brakuje kolumn kontuzji w danych upadków.\n"
                    "Upewnij się, że silnik kontuzji jest podpięty."
                )
                return
            tmp = falls_df[cols].copy()
            falls_agg = tmp.groupby(["Zawodnik", "Kraj"], as_index=False).agg({
                "Kontuzja (dni)": "max",
                "ΔUM (kontuzja)": "min",
                "ΔForma (kontuzja)": "min",
            })

        # Długość kontuzji w tygodniach
        if "Długość kontuzji (WEEK)" in falls_agg.columns:
            weeks = pd.to_numeric(falls_agg["Długość kontuzji (WEEK)"],
                                  errors="coerce").fillna(0).astype(int)
        else:
            if "Kontuzja (dni)" in falls_agg.columns:
                dd = pd.to_numeric(falls_agg["Kontuzja (dni)"],
                                   errors="coerce").fillna(0).astype(int)
                weeks = dd.map(lambda d: 0 if d <= 5 else (1 + (d - 6) // 7))
            else:
                weeks = pd.Series(0, index=falls_agg.index)
            falls_agg["Długość kontuzji (WEEK)"] = weeks

        try:
            week_val = int(week_val)
        except Exception:
            week_val = 0
        falls_agg["ReturnWeek"] = week_val + weeks

        # Wybór pliku bazy zawodników
        path = filedialog.askopenfilename(
            title="Wybierz plik bazy zawodników do aktualizacji",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx *.xls"), ("Wszystkie pliki", "*.*")]
        )
        if not path:
            return

        def _read_any(p):
            try:
                return pd.read_csv(p)
            except Exception:
                pass
            for args in (
                {"sep": ";"},
                {"sep": ";", "encoding": "cp1250"},
                {"sep": ",", "encoding": "utf-8"},
            ):
                try:
                    return pd.read_csv(p, **args)
                except Exception:
                    continue
            try:
                return pd.read_excel(p)
            except Exception:
                return None

        db = _read_any(path)
        if db is None or db.empty:
            messagebox.showerror("Aktualizacja bazy", "Nie udało się odczytać bazy zawodników.")
            return

        # Normalizacja nagłówków
        cols_lower = {str(c).strip().lower(): c for c in db.columns}

        def _find_col(candidates, default=None):
            for cand in candidates:
                if cand in cols_lower:
                    return cols_lower[cand]
            return default

        col_name = _find_col(["zawodnik", "jumper", "name"])
        col_nat = _find_col(["kraj", "nat", "country", "nation"])
        col_um = _find_col(["um"])
        col_forma = _find_col(["forma", "form"])
        col_kontuzja = _find_col(["kontuzja", "injury"])

        rename_map = {}
        if col_name and col_name != "Zawodnik":
            rename_map[col_name] = "Zawodnik"
        if col_nat and col_nat != "Kraj":
            rename_map[col_nat] = "Kraj"
        if col_um and col_um != "UM":
            rename_map[col_um] = "UM"
        if col_forma and col_forma != "Forma":
            rename_map[col_forma] = "Forma"
        if col_kontuzja and col_kontuzja != "Kontuzja":
            rename_map[col_kontuzja] = "Kontuzja"

        if rename_map:
            db = db.rename(columns=rename_map)

        for req in ["Zawodnik", "Kraj", "UM", "Forma"]:
            if req not in db.columns:
                messagebox.showerror(
                    "Aktualizacja bazy",
                    f"Brakuje kolumny '{req}' w bazie zawodników."
                )
                return

        # przygotuj numeric
        db["UM"] = pd.to_numeric(db["UM"], errors="coerce").fillna(0)
        db["Forma"] = pd.to_numeric(db["Forma"], errors="coerce").fillna(0)
        if "Kontuzja" in db.columns:
            db["Kontuzja"] = pd.to_numeric(db["Kontuzja"], errors="coerce").fillna(0)
        else:
            db["Kontuzja"] = 0

        # Aktualizacja per zawodnik
        updated = 0
        for _, row in falls_agg.iterrows():
            name = str(row.get("Zawodnik", "")).strip()
            nat = str(row.get("Kraj", "")).strip()
            if not name or not nat:
                continue

            dUM = float(row.get("ΔUM (kontuzja)", 0) or 0)
            dFR = float(row.get("ΔForma (kontuzja)", 0) or 0)
            retW = int(row.get("ReturnWeek", 0) or 0)

            mask = (db["Zawodnik"].astype(str).str.strip() == name) & (
                db["Kraj"].astype(str).str.strip() == nat
            )
            if not mask.any():
                continue

            db.loc[mask, "UM"] = (db.loc[mask, "UM"] + dUM).clip(lower=0)
            db.loc[mask, "Forma"] = (db.loc[mask, "Forma"] + dFR).clip(lower=0)
            db.loc[mask, "Kontuzja"] = retW
            updated += int(mask.sum())

        # zapis pliku
        try:
            if path.lower().endswith((".xlsx", ".xls")):
                with pd.ExcelWriter(path, engine="openpyxl", mode="w") as w:
                    db.to_excel(w, index=False, sheet_name="Zawodnicy")
            else:
                # wykryj separator
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        head = fh.read(2000)
                    sep = ";" if head.count(";") >= head.count(",") else ","
                except Exception:
                    sep = ";"
                db.to_csv(path, index=False, sep=sep, encoding="utf-8-sig")
        except Exception as e:
            messagebox.showerror(
                "Aktualizacja bazy",
                f"Nie udało się zapisać bazy zawodników:\n{e}"
            )
            return

        # LOG: Kontuzje S45.csv obok bazy
        try:
            import os as _os
            log_dir = _os.path.dirname(path) or "."
            log_path = _os.path.join(log_dir, "Kontuzje S45.csv")

            # baza: tylko realne kontuzje
            base = falls_agg.copy()
            base["Kontuzja (dni)"] = pd.to_numeric(
                base.get("Kontuzja (dni)", 0), errors="coerce"
            ).fillna(0).astype(int)
            base["Długość kontuzji (WEEK)"] = pd.to_numeric(
                base.get("Długość kontuzji (WEEK)", 0), errors="coerce"
            ).fillna(0).astype(int)
            base = base[(base["Kontuzja (dni)"] > 0) | (base["Długość kontuzji (WEEK)"] > 0)]

            if not base.empty:
                log_df = base[[
                    "Zawodnik", "Kraj",
                    "Kontuzja (dni)",
                    "Długość kontuzji (WEEK)",
                    "ΔUM (kontuzja)",
                    "ΔForma (kontuzja)",
                    "ReturnWeek",
                ]].copy()
                log_df.insert(0, "Zawody", event_name or "")
                log_df.insert(1, "Week", week_val)

                # dopisz / utwórz
                if _os.path.exists(log_path):
                    old = pd.read_csv(log_path, sep=";", encoding="utf-8-sig")
                    log_df = pd.concat([old, log_df], ignore_index=True)
                log_df.to_csv(log_path, sep=";", index=False, encoding="utf-8-sig")
        except Exception:
            # jak log nie wyjdzie, trudno, baza już zaktualizowana
            pass

        messagebox.showinfo(
            "Aktualizacja bazy",
            f"Zaktualizowano bazę zawodników na podstawie upadków.\n"
            f"Liczba zawodników z kontuzją: {updated}"
        )

    def _open_injury_update_dialog():
        import tkinter as tk
        from tkinter import ttk, messagebox

        try:
            parent = self.winfo_toplevel()
        except Exception:
            parent = self

        top = tk.Toplevel(parent)
        top.title("Aktualizacja bazy po upadkach (TEAM)")

        ttk.Label(top, text="Nazwa zawodów (np. S45_WC-M_TEAM):")\
            .grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        e_event = ttk.Entry(top, width=32)
        e_event.grid(row=0, column=1, sticky="w", padx=8, pady=(8, 4))

        ttk.Label(top, text="Tydzień (Week):")\
            .grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        sp_week = ttk.Spinbox(top, from_=0, to=60, width=6)
        sp_week.grid(row=1, column=1, sticky="w", padx=8, pady=(0, 8))
        sp_week.delete(0, "end")
        sp_week.insert(0, "1")

        def _ok():
            try:
                event_name = e_event.get().strip()
            except Exception:
                event_name = ""
            try:
                week_val = int(sp_week.get())
            except Exception:
                week_val = 0
            try:
                top.destroy()
            except Exception:
                pass
            try:
                _apply_injury_updates_to_db(event_name, week_val)
            except Exception as e:
                try:
                    messagebox.showerror("Aktualizacja bazy", f"Wystąpił błąd:\n{e}")
                except Exception:
                    pass

        btns = ttk.Frame(top)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", padx=8, pady=(6, 8))
        ttk.Button(btns, text="OK", command=_ok).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btns, text="Anuluj", command=top.destroy).pack(side=tk.RIGHT)

        try:
            top.update_idletasks()
            x = parent.winfo_rootx() + 80
            y = parent.winfo_rooty() + 80
            top.geometry(f"+{x}+{y}")
            top.lift()
            top.focus_force()
            top.attributes("-topmost", True)
            top.after(250, lambda: top.attributes("-topmost", False))
        except Exception:
            pass

    # przypnij do pseudo-self
    self._apply_injury_updates_to_db = _apply_injury_updates_to_db
    self._open_injury_update_dialog = _open_injury_update_dialog

    # --- MSC: folder z wynikami kwalifikacji MSC ---
    self.msc_m_dir_var = tk.StringVar(master=root, value="./S45/Team S45")
    self.msc_w_dir_var = tk.StringVar(master=root, value="./S45/Team S45")


    # ======= ZMIENNE =======
    excel_path = tk.StringVar(master=root, value="C:/Users/ARZEt/Desktop/Nowy folder (2)/Team S44.xlsx")
    sheet_name = tk.StringVar(master=root, value="Arkusz2")
    hill_name = tk.StringVar(master=root, value="Zakopane")
    k_value = tk.StringVar(master=root, value="125")
    hs_value = tk.StringVar(master=root, value="140")
    meter_value = tk.StringVar(master=root, value="")
    wind_mean_value = tk.StringVar(master=root, value="0.0")
    wind_sd_value = tk.StringVar(master=root, value="0.8")
    gate_value = tk.StringVar(master=root, value="10")
    randomness_value = tk.StringVar(master=root, value="0.35")
    elite_regress_value = tk.StringVar(master=root, value="1.0")

    gate_pts_step = tk.DoubleVar(master=root, value=4.0)
    p_gate_change = tk.DoubleVar(master=root, value=0.06)
    max_gate_delta = tk.IntVar(master=root, value=2)
    wind_phi = tk.DoubleVar(master=root, value=0.75)
    wind_takeoff_gain = tk.DoubleVar(master=root, value=0.5)
    wind_flight_gain = tk.DoubleVar(master=root, value=2.2)
    judges_rho = tk.DoubleVar(master=root, value=0.55)
    seed_value = tk.StringVar(master=root, value="")
    max_sigma = tk.StringVar(master=root, value="")
    style_fall_penalty = tk.StringVar(master=root, value="")
    fall_base = tk.StringVar(master=root, value="")
    fall_distance_gain = tk.StringVar(master=root, value="")

    finalists_n = tk.IntVar(master=root, value=8)
    num_series = tk.IntVar(master=root, value=2)

    outdir = tk.StringVar(master=root, value="wyniki")
    name_pattern = tk.StringVar(master=root, value="TEAM_{hill}_{YYYY-mm-dd_HH-MM}")
    only_save = tk.BooleanVar(master=root, value=False)
    auto_open = tk.BooleanVar(master=root, value=False)

    # ======= NOTEBOOK GŁÓWNY =======
    notebook_main = ttk.Notebook(root)
    notebook_main.pack(fill="both", expand=True)

    # ---------- TAB: Baza zawodników (podpięta) ----------
    tab_db = ttk.Frame(notebook_main)
    notebook_main.add(tab_db, text="Baza zawodników")
    db_frame = PlayerDBFrame(tab_db)
    db_frame.pack(fill="both", expand=True, padx=8, pady=8)

# Przygotowanie tabeli Bazy Zawodników do wyświetlania flag
    try:
        db_tv = db_frame._db_edit_table.tree
        db_tv.configure(show="tree headings")  # Włączenie kolumny obrazka (#0)
        db_tv.heading("#0", text="Zawodnik")
        db_tv.column("#0", width=220, anchor="w")
        
        # Ukrywamy starą kolumnę tekstową 'Zawodnik', bo nazwisko będzie przy fladze w #0
        if "Zawodnik" in list(db_tv["columns"]):
            db_tv.column("Zawodnik", width=0, stretch=False)
            
        db_tv.img_refs = []  # Bufor na obrazy, aby nie zniknęły z pamięci
        print("[DEBUG] Skonfigurowano widok bazy z obsługą flag.")
    except Exception as e:
        print(f"[DEBUG] Nie udało się skonfigurować widoku bazy: {e}")

    # ---------- TAB: Kraje (wybór startujących) ----------
    tab_countries = ttk.Frame(notebook_main)
    notebook_main.add(tab_countries, text="Kraje")

    # auto-odświeżenie przy przełączaniu zakładek
    def _on_tab_changed(event):
        try:
            nb = event.widget
            tab_text = nb.tab(nb.select(), "text")
            if tab_text == "Kraje":
                country_frame.refresh_countries(db_frame)
        except Exception:
            pass
    notebook_main.bind("<<NotebookTabChanged>>", _on_tab_changed)

    country_frame = CountrySelectFrame(tab_countries)
    country_frame.pack(fill="both", expand=True)

    # referencja do DB
    country_frame._db_ref = db_frame

        # wstępne wypełnienie listy krajów z bazy + opóźnione odświeżenie
    try:
        country_frame.populate_from_db(db_frame)
    except Exception:
        pass
    try:
        country_frame.after(800, lambda: country_frame.refresh_countries(db_frame))
    except Exception:
        pass

    # podłącz obserwator zmian bazy
    try:
        _attach_db_refresh(db_frame, country_frame)
    except Exception:
        pass
    except Exception:
        pass

    # ---------- TAB: PARAMETRY ----------
    tab_params = ttk.Frame(notebook_main)
    notebook_main.add(tab_params, text="Parametry")
    tab_params.rowconfigure(0, weight=0)
    tab_params.rowconfigure(1, weight=0)
    tab_params.columnconfigure(0, weight=1)

        # ---------- TAB: CC ----------
    tab_cc = ttk.Frame(notebook_main)
    notebook_main.add(tab_cc, text="CC")

    # pod-notebook CC: Q / Grupy / Puchar
    nb_cc = ttk.Notebook(tab_cc)
    nb_cc.pack(fill="both", expand=True, padx=8, pady=8)

    tab_cc_q        = ttk.Frame(nb_cc)
    tab_cc_groups   = ttk.Frame(nb_cc)
    tab_cc_schedule = ttk.Frame(nb_cc)
    tab_cc_cup      = ttk.Frame(nb_cc)
    tab_cc_final    = ttk.Frame(nb_cc)
    cc_cup_canvas   = None
    cc_final_canvas = None      # canvas dla klasyfikacji końcowej CC

    nb_cc.add(tab_cc_q, text="Q")
    nb_cc.add(tab_cc_groups, text="Grupy")
    nb_cc.add(tab_cc_schedule, text="Terminarz")
    nb_cc.add(tab_cc_cup, text="Puchar")
    nb_cc.add(tab_cc_final, text="Klasyfikacja końcowa")

    # ---------- TAB: SWISS ----------
    tab_swiss = ttk.Frame(notebook_main)
    notebook_main.add(tab_swiss, text="SWISS")

    # pod-notebook SWISS: rundy + tabela + klasyfikacja
    nb_swiss = ttk.Notebook(tab_swiss)
    nb_swiss.pack(fill="both", expand=True, padx=8, pady=8)

    tab_swiss_rounds   = ttk.Frame(nb_swiss)
    tab_swiss_table    = ttk.Frame(nb_swiss)
    tab_swiss_classif  = ttk.Frame(nb_swiss)  # NOWE

    nb_swiss.add(tab_swiss_rounds,  text="Rundy")
    nb_swiss.add(tab_swiss_table,   text="Tabela")
    nb_swiss.add(tab_swiss_classif, text="Klasyfikacja")  # NOWE


    from pathlib import Path as _PathSwiss

    swiss_dir_var = tk.StringVar(master=root, value=str(_PathSwiss("S45/Team S45")))

    # --- górny pasek SWISS (folder + przyciski) ---
    frame_swiss_top = ttk.Frame(tab_swiss_rounds)
    frame_swiss_top.pack(fill="x", padx=8, pady=(8, 4))

    ttk.Label(frame_swiss_top, text="Folder SWISS:").pack(side="left")
    ttk.Entry(frame_swiss_top, textvariable=swiss_dir_var, width=50)\
        .pack(side="left", padx=(4, 4))

    def _swiss_browse():
        p = filedialog.askdirectory(title="Wybierz folder SWISS (S45/Team S45)")
        if p:
            swiss_dir_var.set(p)

    ttk.Button(frame_swiss_top, text="…", width=3, command=_swiss_browse)\
        .pack(side="left", padx=(0, 4))

    ttk.Button(
        frame_swiss_top,
        text="Utwórz 1. rundę z seedów",
        command=lambda: _swiss_generate_first_round_from_seed(),
    ).pack(side="left", padx=(4, 4))

    ttk.Button(
        frame_swiss_top,
        text="Utwórz kolejną rundę",
        command=lambda: _swiss_generate_next_round(),
    ).pack(side="left", padx=(4, 4))

    ttk.Button(
        frame_swiss_top,
        text="Odśwież rundy",
        command=lambda: _swiss_reload_matches(),
    ).pack(side="left", padx=(4, 4))

    ttk.Button(
        frame_swiss_top,
        text="Przelicz tabelę",
        command=lambda: _swiss_recompute_and_reload_table(),
    ).pack(side="left", padx=(4, 4))

    ttk.Button(
        frame_swiss_top,
        text="Eksport klasyfikacji CSV",
        command=lambda: _swiss_export_classif_csv()
    ).pack(side="left", padx=4)

    # --- SWISS: uzupełnianie wyniku meczu z ostatniego konkursu TEAM ---
    frame_swiss_update = ttk.Frame(tab_swiss_rounds)
    frame_swiss_update.pack(fill="x", padx=8, pady=(0, 4))

    ttk.Label(frame_swiss_update, text="Uzupełnij zaznaczony mecz z wyników TEAM dla:")\
        .pack(side="left")

    swiss_comp_var = tk.StringVar(master=root, value="MEN")
    cmb_swiss_comp = ttk.Combobox(
        frame_swiss_update,
        textvariable=swiss_comp_var,
        values=("MEN", "WOMEN", "MIXED"),
        width=10,
        state="readonly",
    )
    cmb_swiss_comp.pack(side="left", padx=(4, 4))
    try:
        enable_combobox_wheel(cmb_swiss_comp)
    except Exception:
        pass

    ttk.Button(
        frame_swiss_update,
        text="Zapisz do S45_SWISS.csv",
        command=lambda: _swiss_update_from_results(swiss_comp_var.get()),
    ).pack(side="left", padx=(4, 4))

    # --- tabela rund SWISS ---
    frame_swiss_rounds_tbl = ttk.Frame(tab_swiss_rounds)
    frame_swiss_rounds_tbl.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    cols_swiss_matches = [
        "Runda","Mecz",
        "Drużyna1","Kraj1","PktM1","Minipunkty1",
        "Drużyna2","Kraj2","PktM2","Minipunkty2",
    ]

    tv_swiss_rounds = ttk.Treeview(
        frame_swiss_rounds_tbl,
        columns=cols_swiss_matches,
        show="tree headings",  # Włączamy obsługę flag
        height=20,
    )

    vsb_swiss_r = ttk.Scrollbar(frame_swiss_rounds_tbl, orient="vertical", command=tv_swiss_rounds.yview)
    hsb_swiss_r = ttk.Scrollbar(frame_swiss_rounds_tbl, orient="horizontal", command=tv_swiss_rounds.xview)
    tv_swiss_rounds.configure(yscrollcommand=vsb_swiss_r.set, xscrollcommand=hsb_swiss_r.set)

    tv_swiss_rounds.grid(row=0, column=0, sticky="nsew")
    vsb_swiss_r.grid(row=0, column=1, sticky="ns")
    hsb_swiss_r.grid(row=1, column=0, sticky="ew")

    frame_swiss_rounds_tbl.rowconfigure(0, weight=1)
    frame_swiss_rounds_tbl.columnconfigure(0, weight=1)

    for c in cols_swiss_matches:
        anchor = "center" if c in {"Runda","Mecz","PktM1","PktM2"} or c.startswith("Minipunkty") else "w"
        tv_swiss_rounds.heading(c, text=c, anchor=anchor)
        tv_swiss_rounds.column(c, width=90, anchor=anchor)

    # --- tabela klasyfikacji SWISS (FrozenTable: Lp. zamrożone, flaga przy drużynie) ---
    frame_swiss_table_tbl = ttk.Frame(tab_swiss_table)
    frame_swiss_table_tbl.pack(fill="both", expand=True, padx=8, pady=8)

    # prawa część tabeli (bez Lp. i bez Drużyny – Drużyna idzie do kolumny drzewiastej)
    cols_swiss_table = [
        "Kraj",
        "M", "W", "R", "P",
        "PktM",
        "Minipunkty", "MinipunktyM", "MinipunktyW", "MinipunktyX",
        "Buchholz",
    ]

    right_cols_swiss = []
    for c in cols_swiss_table:
        width = 70
        align = "center"
        if c == "Kraj":
            width = 60
        elif c == "PktM":
            width = 80
        elif c == "Buchholz":
            width = 90
        right_cols_swiss.append((c, width, align))

    # tv_swiss_table będzie teraz FrozenTable, a nie goły Treeview
    swiss_widget, tv_swiss_table = create_frozen_table(
        parent=frame_swiss_table_tbl,
        left_key="Lp.",
        left_title="Lp.",
        left_width=60,
        tree_text_key="Drużyna",
        tree_title="Drużyna",
        right_cols=right_cols_swiss,
        image_from_row=lambda r: _flag_cached(str(r.get("Kraj", "")).strip()),
        height=20,
    )
    swiss_widget.pack(fill="both", expand=True)

    # --- uproszczona klasyfikacja SWISS (FrozenTable z flagą) ---
    swiss_classif_ft = None          # FrozenTable z widokiem
    _swiss_classif_last_df = None    # ostatnia klasyfikacja do eksportu (DataFrame)

    def _build_swiss_classif_tab(parent):
        nonlocal swiss_classif_ft
        from tkinter import ttk

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        widget, ft = create_frozen_table(
            parent=frame,
            left_key="Lp.",
            left_title="Lp.",
            left_width=60,
            tree_text_key="Drużyna",
            tree_title="Drużyna",
            right_cols=[
                ("Kraj",        70,  "center"),
                ("Punkty",      80,  "center"),
                ("Finanse",     110, "center"),
                ("Ranking FIS", 90,  "center"),
            ],
            image_from_row=lambda r: _flag_cached(str(r.get("Kraj", "")).strip()),
            height=24,
        )
        widget.pack(fill="both", expand=True)
        swiss_classif_ft = ft
        return frame

    # zbuduj zakładkę „Klasyfikacja”
    _build_swiss_classif_tab(tab_swiss_classif)

    # --- Q: łączna tabela CC z plików S45_Q_CC_M/W/X ---
    from pathlib import Path

    cc_dir_var = tk.StringVar(master=root, value=str(Path("S45/Team S45")))

    # górny pasek (folder + odśwież)
    frame_q_top = ttk.Frame(tab_cc_q)
    frame_q_top.pack(fill="x", padx=8, pady=(8, 4))

    ttk.Label(frame_q_top, text="Folder Q CC:").pack(side="left")
    ttk.Entry(frame_q_top, textvariable=cc_dir_var, width=50)\
        .pack(side="left", padx=(4, 4))

    # tabela
    frame_q_tbl = ttk.Frame(tab_cc_q)
    frame_q_tbl.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # Używamy FrozenTable: Lp. (lewa), Drużyna z flagą (prawa/drzewo)
    cols_cc_right = [
        ("Kraj", 70, "center"),
        ("MEN", 80, "center"),
        ("WOMEN", 80, "center"),
        ("MIX", 80, "center"),
        ("Suma", 90, "center")
    ]
    
    # Tworzymy tabelę zamrożoną
    cc_q_widget, tv_cc_q = create_frozen_table(
        parent=frame_q_tbl,
        left_key="Lp.",
        left_title="Lp.",
        left_width=60,
        tree_text_key="Drużyna",
        tree_title="Drużyna",
        right_cols=cols_cc_right,
        image_from_row=lambda r: _flag_cached(str(r.get("Kraj", "")).strip()),
        height=18
    )
    cc_q_widget.pack(fill="both", expand=True)

    # --- MSC: grupy + terminarz osobno dla MEN / WOMEN ---
    # msc_groups["M"]["A"] -> FrozenTable dla grupy A w MSC-MEN
    # msc_groups["W"]["B"] -> FrozenTable dla grupy B w MSC-WOMEN
    msc_groups = {"M": {}, "W": {}}
    # terminarz: tv_msc_schedule["M"] / tv_msc_schedule["W"]
    tv_msc_schedule = {"M": None, "W": None}

    # słownik na tabele grup CC (FrozenTable)
    cc_groups: dict[str, FrozenTable] = {}

    # MSC: canvas pucharu (osobno dla MEN / WOMEN)
    msc_cup_canvas = {"M": None, "W": None}
    # MSC: canvas klasyfikacji końcowej (osobno dla MEN / WOMEN)
    msc_classif_canvas = {"M": None, "W": None}

    # pojedyncza tabela na terminarz grup CC
    tv_cc_schedule = None  # typu ttk.Treeview, ustawiane w _build_cc_schedule_tab
    cc_cup_canvas   = None

    def _cc_final_draw(df):
        """Rysuje klasyfikację końcową CC na canvasie – flaga przy drużynie, szerokość na full."""
        import pandas as _pd
        nonlocal cc_final_canvas

        if cc_final_canvas is None:
            return
        c = cc_final_canvas

        # czyścimy wszystko
        c.delete("all")
        if not hasattr(c, "img_refs"):
            c.img_refs = []
        else:
            c.img_refs.clear()

        if df is None or (isinstance(df, _pd.DataFrame) and df.empty):
            c.configure(scrollregion=(0, 0, 0, 0))
            return

        # kolumny
        cols = [
            "Lp.",
            "Drużyna",
            "Kraj",
            "Finanse (miejsce)",
            "Finanse (punkty)",
            "Finanse (suma)",
            "Ranking FIS",
        ]

        for col in cols:
            if col not in df.columns:
                df[col] = _pd.NA

        margin_x = 20
        margin_y = 20
        row_h = 26

        # bazowe szerokości (bez Drużyny, ta dostanie resztę)
        col_widths = {
            "Lp.": 50,
            "Drużyna": 200,           # minimalna, potem dostanie nadwyżkę
            "Kraj": 70,
            "Finanse (miejsce)": 120,
            "Finanse (punkty)": 130,
            "Finanse (suma)": 130,
            "Ranking FIS": 90,
        }

        base_total = sum(col_widths[name] for name in cols)

        # bieżąca szerokość canvasa
        try:
            current_w = c.winfo_width()
        except Exception:
            current_w = 0

        min_w = base_total + 2 * margin_x
        width = max(current_w, min_w)

        extra = width - (base_total + 2 * margin_x)
        if extra > 0:
            col_widths["Drużyna"] += extra

        # wylicz pozycje X
        col_centers: dict[str, float] = {}
        dru_left = None
        x = margin_x
        for name in cols:
            w = col_widths[name]
            if name == "Drużyna":
                dru_left = x
                # dla nagłówka i tekstu drużyny użyjemy lewego brzegu
                col_centers[name] = x
            else:
                col_centers[name] = x + w / 2.0
            x += w

        header_y = margin_y

        # nagłówki
        for name in cols:
            if name == "Drużyna":
                xh = dru_left
                anchor = "w"
            else:
                xh = col_centers[name]
                anchor = "center"
            c.create_text(
                xh,
                header_y,
                text=name,
                anchor=anchor,
                font=("TkDefaultFont", 9, "bold"),
            )

        c.create_line(
            margin_x,
            header_y + 8,
            width - margin_x,
            header_y + 8,
        )

        def _fmt_plain(v):
            if _pd.isna(v):
                return ""
            try:
                f = float(v)
                if abs(f - int(f)) < 1e-6:
                    return str(int(f))
                return str(f)
            except Exception:
                return str(v)

        def _fmt_group(v):
            """Formatowanie z odstępem co 3 cyfry: 3000 -> '3 000'."""
            if _pd.isna(v):
                return ""
            try:
                f = float(v)
                iv = int(round(f))
                s = f"{iv:,}".replace(",", " ")
                return s
            except Exception:
                return _fmt_plain(v)

        y = header_y + row_h

        for _, row in df.iterrows():
            lp        = _fmt_plain(row["Lp."])
            team      = str(row["Drużyna"] or "")
            nat       = str(row["Kraj"] or "").strip().upper()
            fin_place = _fmt_group(row["Finanse (miejsce)"])
            fin_pts   = _fmt_group(row["Finanse (punkty)"])
            fin_sum   = _fmt_group(row["Finanse (suma)"])
            rank      = _fmt_group(row["Ranking FIS"])

            # Lp.
            c.create_text(col_centers["Lp."], y, text=lp, anchor="center")

            # Drużyna + flaga (tu jest flaga)
            img = _flag_cached(nat)
            if img:
                c.img_refs.append(img)
                c.create_image(dru_left, y, image=img, anchor="w")
                c.create_text(dru_left + 22, y, text=team, anchor="w")
            else:
                c.create_text(dru_left, y, text=team, anchor="w")

            # reszta kolumn – wycentrowana
            c.create_text(col_centers["Kraj"], y, text=nat, anchor="center")
            c.create_text(col_centers["Finanse (miejsce)"], y, text=fin_place, anchor="center")
            c.create_text(col_centers["Finanse (punkty)"], y, text=fin_pts, anchor="center")
            c.create_text(col_centers["Finanse (suma)"], y, text=fin_sum, anchor="center")
            c.create_text(col_centers["Ranking FIS"], y, text=rank, anchor="center")

            y += row_h

        c.configure(scrollregion=(0, 0, width, y + margin_y))

    # --- CC: losowanie grup z kwalifikacji CC ---

    # prosty helper do szukania kolumn po nazwie
    def _col(df, candidates, prefix_ok=False):
        """
        Zwraca rzeczywistą nazwę kolumny z df, pasującą do którejś z nazw
        w `candidates` (po przycięciu i bez rozróżniania wielkości liter).
        Jeśli prefix_ok=True, dopuszcza także dopasowanie po prefiksie.
        """
        if df is None or not hasattr(df, "columns"):
            return None

        cols = list(df.columns)
        norm = [str(c).strip().lower() for c in cols]

        for cand in candidates:
            cand_norm = str(cand).strip().lower()

            # 1) pełne dopasowanie
            for i, cname in enumerate(norm):
                if cname == cand_norm:
                    return cols[i]

            # 2) dopasowanie po prefiksie, jeśli wolno
            if prefix_ok:
                for i, cname in enumerate(norm):
                    if cname.startswith(cand_norm):
                        return cols[i]

        return None

    def _cc_read_q_csv_any(path: Path) -> pd.DataFrame:
        """Bezpieczne wczytanie pliku S45_Q_CC_*.csv (różne separatory/kodowania)."""
        last_err = None
        for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
            try:
                return pd.read_csv(path, sep=None, engine="python", encoding=enc)
            except Exception as e:
                last_err = e
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8-sig")
        except Exception:
            raise RuntimeError(f"Nie mogę wczytać pliku CC: {path}\n{last_err}")

    def _cc_norm_header(s: str) -> str:
        s = str(s or "").strip().lower()
        import unicodedata, re
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"[^a-z0-9]+", "", s)
        return s

    def _cc_pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
        """Znajdź kolumnę po znormalizowanej nazwie (Drużyna/Kraj/Punkty itd.)."""
        if df is None or df.empty:
            return None
        low = { _cc_norm_header(c): c for c in df.columns }
        for cand in candidates:
            key = _cc_norm_header(cand)
            if key in low:
                return low[key]
        # prefiksy typu "punktydlaq"
        for cand in candidates:
            key = _cc_norm_header(cand)
            for k, orig in low.items():
                if k.startswith(key):
                    return orig
        return None

    def _cc_q_summary_from_dir(dir_path: Path) -> pd.DataFrame:
        """
        Czyta:
        S45_Q_CC_M.csv, S45_Q_CC_W.csv, S45_Q_CC_X.csv
        i buduje tabelę:
        Lp., Drużyna, Kraj, MEN, WOMEN, MIX, Suma
        """
        data = {}  # (team, nat) -> {"MEN":..., "WOMEN":..., "MIX":...}

        for suffix, col_name in (("M", "MEN"), ("W", "WOMEN"), ("X", "MIX")):
            p = dir_path / f"S45_Q_CC_{suffix}.csv"
            if not p.is_file():
                continue

            try:
                df_raw = _cc_read_q_csv_any(p)
            except Exception as e:
                print("DEBUG CC: problem z wczytaniem", p, "->", e)
                continue

            team_col = _cc_pick_col(df_raw, ["Drużyna", "Druzyna", "Team", "Reprezentacja", "Nation"])
            nat_col  = _cc_pick_col(df_raw, ["Kraj", "NAT", "Code", "Nation code"])
            pts_col  = _cc_pick_col(df_raw, ["Suma", "PTS", "Punkty", "Punkty dla Q"])

            if not team_col or not nat_col or not pts_col:
                print("DEBUG CC:", p, "brak kolumn (team/nat/pts)", df_raw.columns)
                continue

            df = df_raw[[team_col, nat_col, pts_col]].copy()
            df[team_col] = df[team_col].astype(str).str.strip()
            df[nat_col]  = df[nat_col].astype(str).str.upper().str.strip()
            df[pts_col]  = pd.to_numeric(df[pts_col], errors="coerce").fillna(0.0)

            for _, r in df.iterrows():
                key = (r[team_col], r[nat_col])
                if not key[0] or not key[1]:
                    continue
                bucket = data.setdefault(key, {"MEN": 0.0, "WOMEN": 0.0, "MIX": 0.0})
                bucket[col_name] += float(r[pts_col])

        if not data:
            return pd.DataFrame(columns=["Lp.", "Drużyna", "Kraj", "MEN", "WOMEN", "MIX", "Suma"])

        rows = []
        for (team, nat), vals in data.items():
            men = float(vals.get("MEN", 0.0) or 0.0)
            wom = float(vals.get("WOMEN", 0.0) or 0.0)
            mix = float(vals.get("MIX", 0.0) or 0.0)
            suma = men + wom + mix
            rows.append({
                "Drużyna": team,
                "Kraj": nat,
                "MEN": men,
                "WOMEN": wom,
                "MIX": mix,
                "Suma": suma,
            })

        out = pd.DataFrame(rows)
        out = out.sort_values("Suma", ascending=False, kind="stable").reset_index(drop=True)
        out.insert(0, "Lp.", np.arange(1, len(out) + 1))
        return out

    def _msc_draw_groups_for_dir(dir_str: str, sex: str):
        """
        Losuje grupy A–D z TOP16 z kwalifikacji MSC (dla danej płci)
        i zapisuje:
          S45_MSC_<sex>_Grupa_A.csv ... S45_MSC_<sex>_Grupa_D.csv
        w wybranym folderze.
        """
        from tkinter import messagebox
        from pathlib import Path
        import pandas as pd

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            messagebox.showerror("MSC – grupy", f"Nieprawidłowe sex={sex!r}")
            return

        dir_path = Path(dir_str.strip() or ".")
        if not dir_path.is_dir():
            messagebox.showerror("MSC – grupy", f"Folder MSC nie istnieje:\n{dir_path}")
            return

        try:
            df_q = _msc_q_summary_from_dir(dir_path, sex=sex)
        except Exception as e:
            messagebox.showerror("MSC – grupy", f"Problem z kwalifikacjami MSC:\n{e}")
            return

        if df_q.empty or len(df_q) < 16:
            messagebox.showerror(
                "MSC – grupy",
                f"Za mało drużyn w kwalifikacjach MSC-{sex} (mam {len(df_q)}, potrzebuję ≥16).",
            )
            return

        top16 = df_q.head(16).copy().reset_index(drop=True)

        # koszyki wg Lp.: 1–4, 5–8, 9–12, 13–16
        basket_ids = []
        for idx in range(len(top16)):
            lp = idx + 1
            if lp <= 4:
                basket_ids.append(1)
            elif lp <= 8:
                basket_ids.append(2)
            elif lp <= 12:
                basket_ids.append(3)
            else:
                basket_ids.append(4)
        top16["Koszyk"] = basket_ids

        rng = np.random.default_rng()
        group_labels = ["A", "B", "C", "D"]
        groups: dict[str, list[dict]] = {g: [] for g in group_labels}

        # z każdego koszyka losowo rozkładamy po 1 drużynie do każdej grupy
        for b in (1, 2, 3, 4):
            pool = top16[top16["Koszyk"] == b].index.to_list()
            if len(pool) < 4:
                messagebox.showerror(
                    "MSC – grupy",
                    f"Koszyk {b} ma tylko {len(pool)} drużyny. Sprawdź kwalifikacje MSC-{sex}.",
                )
                return
            rng.shuffle(pool)
            for g_idx, g in enumerate(group_labels):
                idx = pool[g_idx]
                row = top16.loc[idx]
                groups[g].append({
                    "Drużyna": row["Drużyna"],
                    "Kraj": row["Kraj"],
                })

        # zapis czterech plików dla danej płci:
        # S45_MSC_M_Grupa_A.csv, ..., S45_MSC_W_Grupa_D.csv
        for g in group_labels:
            recs = []
            for lp, row in enumerate(groups[g], start=1):
                recs.append({
                    "Lp.": lp,
                    "Drużyna": row["Drużyna"],
                    "Kraj": row["Kraj"],
                    "Punkty Zdobyte": 0,
                    "Punkty Stracone": 0,
                    "Minipunkty": 0,
                })
            df_g = pd.DataFrame(
                recs,
                columns=["Lp.", "Drużyna", "Kraj", "Punkty Zdobyte", "Punkty Stracone", "Minipunkty"],
            )
            out_path = dir_path / f"S45_MSC_{sex}_Grupa_{g}.csv"
            try:
                df_g.to_csv(out_path, sep=";", encoding="cp1250", index=False)
            except Exception:
                df_g.to_csv(out_path, sep=";", encoding="utf-8-sig", index=False)

        messagebox.showinfo(
            "MSC – grupy",
            f"Wylosowano grupy MSC-{sex} i zapisano:\n"
            "S45_MSC_{sex}_Grupa_A.csv … S45_MSC_{sex}_Grupa_D.csv",
        )

    def _msc_groups_reload(sex: str):
        """Wczytuje S45_MSC_<sex>_Grupa_A…D.csv i odświeża tabelki MSC."""
        from pathlib import Path
        import pandas as pd

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            return

        dir_var = self.msc_m_dir_var if sex == "M" else self.msc_w_dir_var
        dir_path = Path(dir_var.get().strip() or ".")
        cols = ["Lp.", "Drużyna", "Kraj", "Punkty Zdobyte", "Punkty Stracone", "Minipunkty"]

        group_map = msc_groups.get(sex, {})

        for g, ft in group_map.items():
            ft.clear()
            p = dir_path / f"S45_MSC_{sex}_Grupa_{g}.csv"
            if not p.is_file():
                continue
            try:
                df = _cc_read_q_csv_any(p)  # mamy już odporny reader
            except Exception as e:
                print("MSC grupy:", p, "->", e)
                continue

            for col in cols:
                if col not in df.columns:
                    if col in ("Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
                        df[col] = 0
                    else:
                        df[col] = ""
            df = df[cols]

            for _, r in df.iterrows():
                ft.insert_row(dict(r))

        # po odświeżeniu grup spróbuj od razu zbudować terminarz
        try:
            _msc_schedule_reload(sex)
        except Exception:
            pass

    def _msc_collect_groups(sex: str):
        """
        Zbiera skład grup MSC dla danej płci z tabelek FrozenTable.

        Zwraca:
            { "A": [(team, nat), ...], "B": [...], ... }
        """
        sex = str(sex or "").upper()[:1]
        groups: dict[str, list[tuple[str, str]]] = {}
        group_map = msc_groups.get(sex, {})
        for g, ft in group_map.items():
            rows: list[tuple[str, str]] = []
            try:
                tv = ft.tvR
            except Exception:
                continue
            for iid in tv.get_children(""):
                item = tv.item(iid)
                team = str(item.get("text", "")).strip()
                vals = item.get("values", ())
                nat = str(vals[0]).strip() if vals else ""
                if team and nat:
                    rows.append((team, nat))
            if rows:
                groups[g] = rows
        return groups

    def _msc_schedule_reload(sex: str):
        """
        Odświeża tabelę terminarza MSC (dla danej płci) na podstawie aktualnych grup.
        """
        sex = str(sex or "").upper()[:1]
        tv = tv_msc_schedule.get(sex)
        if tv is None:
            return

        groups = _msc_collect_groups(sex)
        schedule_list = _cc_build_group_schedule(groups)  # ta sama logika co w CC

        tv.delete(*tv.get_children(""))
        for row in schedule_list:
            tv.insert(
                "",
                "end",
                values=(
                    row["Kolejka"],
                    row["Grupa"],
                    row["Mecz"],
                    row["Drużyna1"],
                    row["Kraj1"],
                    row["Drużyna2"],
                    row["Kraj2"],
                ),
            )

    def _build_msc_groups_tab(parent, sex: str):
        """Buduje zakładkę 'Grupy' dla MSC-MEN / MSC-WOMEN."""
        from tkinter import ttk

        sex = str(sex or "").upper()[:1]
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 4))

        ttk.Button(
            top,
            text="Odśwież z plików",
            command=lambda s=sex: _msc_groups_reload(s),
        ).pack(side="right")

        grid = ttk.Frame(frame)
        grid.pack(fill="both", expand=True)

        for r in range(4):
            grid.rowconfigure(r, weight=1)
        grid.columnconfigure(0, weight=1)

        group_map = msc_groups[sex]

        for row, g in enumerate(("A", "B", "C", "D")):
            box = ttk.Labelframe(grid, text=f"Grupa {g}")
            box.grid(row=row, column=0, sticky="nsew", padx=4, pady=4)

            widget, ft = create_frozen_table(
                parent=box,
                left_key="Lp.",
                left_title="Lp.",
                left_width=60,
                tree_text_key="Drużyna",
                tree_title="Drużyna",
                right_cols=[
                    ("Kraj", 70, "center"),
                    ("Punkty Zdobyte", 120, "center"),
                    ("Punkty Stracone", 120, "center"),
                    ("Minipunkty", 120, "center"),
                ],
                image_from_row=lambda r, _g=g: _flag_cached(str(r.get("Kraj", "")).strip()),
                height=6,
            )
            widget.pack(fill="both", expand=True)

            group_map[g] = ft

        return frame

    def _build_msc_schedule_tab(parent, sex: str):
        """Buduje zakładkę 'Terminarz' dla MSC-MEN / MSC-WOMEN."""
        from tkinter import ttk
        nonlocal tv_msc_schedule

        sex = str(sex or "").upper()[:1]
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 4))

        ttk.Button(
            top,
            text="Generuj terminarz z grup",
            command=lambda s=sex: _msc_schedule_reload(s),
        ).pack(side="left")

        frame_tbl = ttk.Frame(frame)
        frame_tbl.pack(fill="both", expand=True)

        tv = ttk.Treeview(
            frame_tbl,
            columns=("Kolejka", "Grupa", "Mecz", "Drużyna1", "Kraj1", "Drużyna2", "Kraj2"),
            show="headings",
            height=18,
        )

        vsb = ttk.Scrollbar(frame_tbl, orient="vertical", command=tv.yview)
        hsb = ttk.Scrollbar(frame_tbl, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        frame_tbl.rowconfigure(0, weight=1)
        frame_tbl.columnconfigure(0, weight=1)

        for c in ("Kolejka", "Grupa", "Mecz", "Drużyna1", "Kraj1", "Drużyna2", "Kraj2"):
            anchor = "center" if c in ("Kolejka", "Grupa", "Mecz", "Kraj1", "Kraj2") else "w"
            tv.heading(c, text=c)
            tv.column(c, width=80, anchor=anchor)

        tv_msc_schedule[sex] = tv
        return frame

    def _msc_classif_reload(sex: str):
        """
        Klasyfikacja MSC dla danej płci:
        - miejsca 1–16 z meczów M7, M8, M11, M12, M15, M16, M19, M20 z pliku <sezon>_MSC_<sex>_Puchar.csv
        - miejsca 17+ z kwalifikacji MSC (punkty z Q)
        - kolumny: Lp., Drużyna, Kraj, Punkty, Finanse (miejsce), Finanse (suma), Ranking FIS
        """
        from tkinter import messagebox
        from pathlib import Path
        import pandas as _pd
        import re as _re

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            return

        dir_var = self.msc_m_dir_var if sex == "M" else self.msc_w_dir_var
        dir_path = Path(dir_var.get().strip() or ".").resolve()
        if not dir_path.is_dir():
            messagebox.showerror("MSC – Klasyfikacja", f"Folder MSC nie istnieje:\n{dir_path}")
            _msc_classif_redraw_canvas(sex, None)
            return

        # --- Q MSC ---
        try:
            df_q = _msc_q_summary_from_dir(dir_path, sex=sex)
        except Exception as e:
            print(f"[MSC-Klasa] Brak pliku kwalifikacji ({sex}): {e}")
            _msc_classif_redraw_canvas(sex, None)
            return

        if df_q is None or df_q.empty:
            print(f"[MSC-Klasa] Brak danych kwalifikacji MSC ({sex}).")
            _msc_classif_redraw_canvas(sex, None)
            return

        df_q = df_q.copy()
        df_q["Drużyna"] = df_q["Drużyna"].astype(str).str.strip()
        df_q["Kraj"] = df_q["Kraj"].astype(str).str.strip().str.upper()
        df_q["Punkty"] = _pd.to_numeric(df_q["Punkty"], errors="coerce").fillna(0.0)

        # sortowanie po punktach (Q)
        df_q = df_q.sort_values(by=["Punkty", "Drużyna"], ascending=[False, True]).reset_index(drop=True)
        q_order = {(r["Drużyna"], r["Kraj"]): idx for idx, r in df_q.iterrows()}

        # --- Puchar MSC ---
        season = dir_path.parent.name if dir_path.parent.name else "S45"
        cup_path = dir_path / f"{season}_MSC_{sex}_Puchar.csv"

        df_cup = None
        places_from_cup: dict[tuple[str, str], int] = {}

        if cup_path.is_file():
            last_err = None
            for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
                try:
                    df_cup = _pd.read_csv(cup_path, sep=None, engine="python", encoding=enc)
                    break
                except Exception as e:
                    last_err = e
                    df_cup = None
            if df_cup is None:
                try:
                    df_cup = _pd.read_csv(cup_path, sep=";", encoding="utf-8-sig")
                except Exception:
                    messagebox.showerror(
                        "MSC – Klasyfikacja",
                        f"Nie mogę wczytać pliku pucharu MSC:\n{cup_path}\n{last_err}"
                    )
                    _msc_classif_redraw_canvas(sex, None)
                    return

            # proste mapowanie nagłówków
            norm = {str(c).strip().lower(): c for c in df_cup.columns}
            col_m  = norm.get("mecz")
            col_t1 = norm.get("drużyna1") or norm.get("druzyna1")
            col_k1 = norm.get("kraj1")
            col_p1 = norm.get("punkty1")
            col_t2 = norm.get("drużyna2") or norm.get("druzyna2")
            col_k2 = norm.get("kraj2")
            col_p2 = norm.get("punkty2")

            if not all([col_m, col_t1, col_k1, col_p1, col_t2, col_k2, col_p2]):
                df_cup = None  # jak brakuje kolumn, nie bawimy się w top16

        # mecze o miejsca:
        # M7, M8, M11, M12, M15, M16, M19, M20 -> kolejno 1,3,5,7,9,11,13,15
        match_map = {
            7: 1,
            8: 3,
            11: 5,
            12: 7,
            15: 9,
            16: 11,
            19: 13,
            20: 15,
        }

        if df_cup is not None:
            for _, row in df_cup.iterrows():
                raw_m = str(row.get(col_m, "") or "").strip()
                m = _re.search(r"\d+", raw_m)
                if not m:
                    continue
                m_no = int(m.group(0))
                base_place = match_map.get(m_no)
                if not base_place:
                    continue

                t1 = str(row.get(col_t1, "") or "").strip()
                k1 = str(row.get(col_k1, "") or "").strip().upper()
                t2 = str(row.get(col_t2, "") or "").strip()
                k2 = str(row.get(col_k2, "") or "").strip().upper()
                try:
                    p1 = float(row.get(col_p1, 0) or 0)
                except Exception:
                    p1 = 0.0
                try:
                    p2 = float(row.get(col_p2, 0) or 0)
                except Exception:
                    p2 = 0.0

                if not (t1 and k1 and t2 and k2):
                    continue

                key1 = (t1, k1)
                key2 = (t2, k2)

                if p1 > p2:
                    places_from_cup[key1] = base_place
                    places_from_cup[key2] = base_place + 1
                elif p2 > p1:
                    places_from_cup[key2] = base_place
                    places_from_cup[key1] = base_place + 1
                else:
                    # remis -> lepsze miejsce z Q
                    pos1 = q_order.get(key1, 9999)
                    pos2 = q_order.get(key2, 9999)
                    if pos1 <= pos2:
                        places_from_cup[key1] = base_place
                        places_from_cup[key2] = base_place + 1
                    else:
                        places_from_cup[key2] = base_place
                        places_from_cup[key1] = base_place + 1

        # --- składanie klasyfikacji ---
        rows = []
        used_pairs = set()

        # miejsca z pucharu (1–16)
        for _, r in df_q.iterrows():
            key = (r["Drużyna"], r["Kraj"])
            place = places_from_cup.get(key)
            if place is None:
                continue
            rows.append(
                {
                    "Lp.": int(place),
                    "Drużyna": r["Drużyna"],
                    "Kraj": r["Kraj"],
                    "Punkty": float(r["Punkty"]),
                }
            )
            used_pairs.add(key)

        # ogony z Q (17+)
        if places_from_cup:
            max_place = max(places_from_cup.values())
            next_place = max(max_place + 1, 17)
        else:
            next_place = 1

        for _, r in df_q.iterrows():
            key = (r["Drużyna"], r["Kraj"])
            if key in used_pairs:
                continue
            rows.append(
                {
                    "Lp.": int(next_place),
                    "Drużyna": r["Drużyna"],
                    "Kraj": r["Kraj"],
                    "Punkty": float(r["Punkty"]),
                }
            )
            next_place += 1

        if not rows:
            print("[MSC-Klasa] Nie udało się zbudować żadnej klasyfikacji MSC.")
            _msc_classif_redraw_canvas(sex, None)
            return

        df_final = _pd.DataFrame(rows)
        df_final = df_final.sort_values("Lp.").reset_index(drop=True)

        # --- Finanse + Ranking FIS (jak w CC) ---
        prize_by_place = {
            1: 300_000,
            2: 250_000,
            3: 200_000,
            4: 150_000,
            5: 125_000,
            6: 100_000,
            7: 75_000,
            8: 62_500,
            9: 50_000,
            10: 40_000,
            11: 30_000,
            12: 25_000,
            13: 20_000,
            14: 17_500,
            15: 15_000,
            16: 12_500,
        }
        ranking_fis_by_place = {
            1: 200,
            2: 150,
            3: 100,
            4: 70,
            5: 50,
            6: 30,
            7: 20,
            8: 10,
            9: 5,
            10: 3,
        }

        def _place_prize(p):
            try:
                p = int(p)
            except Exception:
                return 0
            return prize_by_place.get(p, 10_000)

        def _place_ranking(p):
            try:
                p = int(p)
            except Exception:
                return 0
            return ranking_fis_by_place.get(p, 0)

        df_final["Finanse (miejsce)"] = df_final["Lp."].apply(_place_prize).astype(int)
        df_final["Finanse (suma)"] = df_final["Finanse (miejsce)"].astype(int)
        df_final["Ranking FIS"] = df_final["Lp."].apply(_place_ranking).astype(int)

        # odśwież rysunek w GUI
        _msc_classif_redraw_canvas(sex, df_final)

        # --- zapis do CSV ---
        try:
            # sezon = nazwa folderu nadrzędnego (np. S45)
            season = dir_path.parent.name if dir_path.parent.name else "S45"
            out_name = f"{season}_MSC_{sex}_Klasyfikacja.csv"
            out_path = dir_path / out_name

            df_save = df_final.copy()
            df_save.to_csv(out_path, sep=";", encoding="utf-8-sig", index=False)
            print("[MSC-Klasa] zapisano klasyfikację do", out_path)
        except Exception as e:
            print("[MSC-Klasa] błąd przy zapisie CSV:", e)

    def _msc_classif_redraw_canvas(sex: str, df):
        """Rysuje klasyfikację MSC dla danej płci na canvasie (flaga, drużyna, finanse, ranking)."""
        import pandas as _pd
        import tkinter as tk

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            return

        c = msc_classif_canvas.get(sex)
        if c is None:
            return

        c.delete("all")
        if not hasattr(c, "img_refs"):
            c.img_refs = []
        else:
            c.img_refs.clear()

        if df is None or (isinstance(df, _pd.DataFrame) and df.empty):
            c.configure(scrollregion=(0, 0, 0, 0))
            return

        # wymagane kolumny
        for col in ["Lp.", "Drużyna", "Kraj", "Punkty", "Finanse (miejsce)", "Finanse (suma)", "Ranking FIS"]:
            if col not in df.columns:
                df[col] = 0

        df = df.copy()
        df["Drużyna"] = df["Drużyna"].astype(str)
        df["Kraj"] = df["Kraj"].astype(str).str.upper()

        margin_x = 10
        margin_y = 10
        row_h = 24

        col_order = ["Lp.", "Drużyna", "Kraj", "Punkty", "Finanse (miejsce)", "Finanse (suma)", "Ranking FIS"]
        col_widths = {
            "Lp.": 40,
            "Drużyna": 260,
            "Kraj": 60,
            "Punkty": 80,
            "Finanse (miejsce)": 130,
            "Finanse (suma)": 130,
            "Ranking FIS": 80,
        }

        current_w = c.winfo_width() or 0
        width = max(current_w, 900)
        base_total = sum(col_widths.values())
        extra = max(width - (base_total + 2 * margin_x), 0)
        col_widths["Drużyna"] += extra

        col_centers = {}
        dru_left = None
        x = margin_x
        for name in col_order:
            w = col_widths[name]
            if name == "Drużyna":
                dru_left = x
                col_centers[name] = x
            else:
                col_centers[name] = x + w / 2.0
            x += w

        header_y = margin_y
        for name in col_order:
            if name == "Drużyna":
                xh = dru_left
                anchor = "w"
            else:
                xh = col_centers[name]
                anchor = "center"
            c.create_text(
                xh,
                header_y,
                text=name,
                anchor=anchor,
                font=("TkDefaultFont", 9, "bold"),
            )

        c.create_line(
            margin_x,
            header_y + 8,
            width - margin_x,
            header_y + 8,
        )

        def _fmt_plain(v):
            if _pd.isna(v):
                return ""
            try:
                f = float(v)
                if abs(f - int(f)) < 1e-6:
                    return str(int(f))
                return str(f)
            except Exception:
                return str(v)

        def _fmt_money(v):
            try:
                n = int(round(float(v)))
            except Exception:
                return ""
            return f"{n:,}".replace(",", " ")

        y = header_y + row_h
        for _, row in df.iterrows():
            lp = _fmt_plain(row["Lp."])
            team = str(row["Drużyna"] or "")
            nat = str(row["Kraj"] or "").strip().upper()
            pts = _fmt_plain(row["Punkty"])
            fin_place = _fmt_money(row["Finanse (miejsce)"])
            fin_sum = _fmt_money(row["Finanse (suma)"])
            rank = _fmt_plain(row["Ranking FIS"])

            # Lp.
            c.create_text(col_centers["Lp."], y, text=lp, anchor="center")

            # Drużyna + flaga
            img = _flag_cached(nat)
            if img:
                c.img_refs.append(img)
                c.create_image(dru_left, y, image=img, anchor="w")
                c.create_text(dru_left + 22, y, text=team, anchor="w")
            else:
                c.create_text(dru_left, y, text=team, anchor="w")

            c.create_text(col_centers["Kraj"], y, text=nat, anchor="center")
            c.create_text(col_centers["Punkty"], y, text=pts, anchor="center")
            c.create_text(col_centers["Finanse (miejsce)"], y, text=fin_place, anchor="center")
            c.create_text(col_centers["Finanse (suma)"], y, text=fin_sum, anchor="center")
            c.create_text(col_centers["Ranking FIS"], y, text=rank, anchor="center")

            y += row_h

        c.configure(scrollregion=(0, 0, width, y + margin_y))

    def _build_msc_classif_tab(parent, sex: str):
        """Zakładka 'Klasyfikacja' dla MSC-MEN / MSC-WOMEN."""
        from tkinter import ttk
        import tkinter as tk

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            sex = "M"

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 4))

        ttk.Button(
            top,
            text="Przelicz klasyfikację MSC",
            command=lambda s=sex: _msc_classif_reload(s),
        ).pack(side="left")

        inner = ttk.Frame(frame)
        inner.pack(fill="both", expand=True)

        canvas = tk.Canvas(inner, background="white")
        vsb = ttk.Scrollbar(inner, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)

        def _on_mousewheel(event):
            if hasattr(event, "delta") and event.delta:
                step = -1 if event.delta > 0 else 1
            else:
                num = getattr(event, "num", None)
                if num == 4:
                    step = -1
                elif num == 5:
                    step = 1
                else:
                    step = 0
            if step:
                canvas.yview_scroll(step, "units")
            return "break"

        canvas.bind("<MouseWheel>", _on_mousewheel)
        canvas.bind("<Button-4>", _on_mousewheel)
        canvas.bind("<Button-5>", _on_mousewheel)

        msc_classif_canvas[sex] = canvas
        canvas.img_refs = []

        return frame

    def _msc_cup_reload(sex: str):
        """
        Wczytuje plik Pucharu MSC dla danej płci i odświeża RYSUNEK na canvasie (tak jak w CC).
        """
        from pathlib import Path
        import pandas as _pd

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            return

        # wybór folderu MSC z GUI
        dir_var = self.msc_m_dir_var if sex == "M" else self.msc_w_dir_var
        root = Path(dir_var.get().strip() or ".").resolve()

        # sezon = nazwa folderu nadrzędnego (np. S45)
        season = root.parent.name if root.parent.name else "S45"
        path = root / f"{season}_MSC_{sex}_Puchar.csv"

        if not path.is_file():
            print("[MSC-Puchar] brak pliku:", path)
            # wyczyść canvas
            _msc_cup_redraw_canvas(sex, _pd.DataFrame())
            return

        # bezpieczne wczytanie
        try:
            df = _cc_read_q_csv_any(path)
        except Exception as e:
            print("[MSC-Puchar] problem z _cc_read_q_csv_any:", e)
            df = None

        if df is None:
            for enc in ("cp1250", "utf-8-sig", "latin-1"):
                try:
                    df = _pd.read_csv(path, sep=";", encoding=enc)
                    break
                except Exception:
                    df = None

        if df is None:
            print("[MSC-Puchar] nie udało się wczytać pliku", path)
            _msc_cup_redraw_canvas(sex, _pd.DataFrame())
            return

        print("[MSC-Puchar] wczytano", path, "rows:", len(df), "cols:", list(df.columns))

        needed = [
            "Mecz", "Faza",
            "Drużyna1", "Kraj1", "Punkty1", "Minipunkty1",
            "Drużyna2", "Kraj2", "Punkty2", "Minipunkty2",
        ]

        # mapowanie po znormalizowanych nagłówkach (jak w CC)
        norm_map: dict[str, str] = {}
        for c in df.columns:
            key = _cc_norm_header(c)
            if key and key not in norm_map:
                norm_map[key] = c

        def _src(col: str) -> str:
            key = _cc_norm_header(col)
            return norm_map.get(key, col)

        rows = []
        for _, r in df.iterrows():
            row = {}
            for col in needed:
                src = _src(col)
                row[col] = r.get(src, "")
            rows.append(row)

        df_norm = _pd.DataFrame(rows, columns=needed)

        _msc_cup_redraw_canvas(sex, df_norm)

    def _msc_cup_redraw_canvas(sex: str, df):
        """Rysuje mecze MSC Cup na canvasie z flagami obu drużyn (tak jak CC, ale per płeć)."""
        import pandas as _pd
        nonlocal msc_cup_canvas

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            return

        canvas = msc_cup_canvas.get(sex)
        if canvas is None:
            return

        c = canvas
        c.delete("all")
        c.img_refs = []   # żeby GC nie zjadł flag

        if df is None or df.empty:
            # nic nie rysujemy, ale czyścimy scrollregion
            c.configure(scrollregion=(0, 0, 0, 0))
            return

        margin_x = 20
        margin_y = 20
        row_h = 80
        box_w = 900

        for i, row in df.iterrows():
            mecz   = str(row.get("Mecz", "")).strip()
            faza   = str(row.get("Faza", "")).strip()
            d1     = str(row.get("Drużyna1", "")).strip()
            nat1   = str(row.get("Kraj1", "")).strip()
            d2     = str(row.get("Drużyna2", "")).strip()
            nat2   = str(row.get("Kraj2", "")).strip()
            p1     = row.get("Punkty1", "")
            p2     = row.get("Punkty2", "")

            y0 = margin_y + i * row_h
            y1 = y0 + row_h - 10

            # czy to mecz o 1/3/5/... miejsce? (kolor tła jak w CC)
            bg_fill = "#f0f0f0"
            try:
                low_faza = faza.lower()
                if "miejsce" in low_faza:
                    import re as _re
                    mnum = _re.search(r"(\d+)", low_faza)
                    if mnum:
                        place = int(mnum.group(1))
                        if place % 2 == 1:  # 1, 3, 5, 7...
                            bg_fill = "#ceab20"
            except Exception:
                pass

            # tło meczu
            c.create_rectangle(
                margin_x, y0,
                margin_x + box_w, y1,
                outline="#555555",
                width=1,
                fill=bg_fill,
            )

            # flagi
            img1 = _flag_cached(nat1) if nat1 else None
            img2 = _flag_cached(nat2) if nat2 else None
            if img1:
                c.img_refs.append(img1)
            if img2:
                c.img_refs.append(img2)

            cy = (y0 + y1) // 2 - 8  # środek pionowo

            # LEWA STRONA – Drużyna1 + flaga
            x = margin_x + 10
            if img1:
                c.create_image(x, cy, image=img1, anchor="w")
                x += 26  # szerokość flagi + odstęp

            c.create_text(
                x, cy,
                text=d1,
                anchor="w",
                font=("TkDefaultFont", 10, "bold"),
            )

            # wynik 1
            txt_p1 = ""
            try:
                if not _pd.isna(p1) and str(p1) != "":
                    txt_p1 = str(p1)
            except Exception:
                txt_p1 = str(p1) if p1 is not None else ""

            c.create_text(
                margin_x + 260, cy,
                text=txt_p1,
                anchor="e",
                font=("TkDefaultFont", 10),
            )

            # dwukropek
            c.create_text(
                margin_x + 280, cy,
                text=":",
                anchor="center",
                font=("TkDefaultFont", 10, "bold"),
            )

            # wynik 2
            txt_p2 = ""
            try:
                if not _pd.isna(p2) and str(p2) != "":
                    txt_p2 = str(p2)
            except Exception:
                txt_p2 = str(p2) if p2 is not None else ""

            c.create_text(
                margin_x + 300, cy,
                text=txt_p2,
                anchor="w",
                font=("TkDefaultFont", 10),
            )

            # PRAWA STRONA – Drużyna2 + flaga
            x2 = margin_x + 500
            c.create_text(
                x2, cy,
                text=d2,
                anchor="e",
                font=("TkDefaultFont", 10, "bold"),
            )
            x2 += 6
            if img2:
                c.create_image(x2, cy, image=img2, anchor="w")

            # podpis fazy na dole pola meczu
            c.create_text(
                margin_x + 10,
                y1 - 12,
                text=f"{faza} ({mecz})" if faza or mecz else "",
                anchor="w",
                fill="#666666",
                font=("TkDefaultFont", 8),
            )

        # ustaw region przewijania
        bbox = c.bbox("all")
        if bbox:
            c.configure(scrollregion=bbox)
        else:
            c.configure(scrollregion=(0, 0, 0, 0))

    def _msc_build_cup_from_groups(dir_str: str, sex: str):
        """
        Buduje drabinkę pucharową MSC (1–16) na podstawie:
          <sezon>_MSC_<sex>_Grupa_A…D.csv
        i zapisuje:
          <sezon>_MSC_<sex>_Puchar.csv
        """
        from tkinter import messagebox
        from pathlib import Path
        import pandas as pd

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            messagebox.showerror("MSC – Puchar", f"Nieprawidłowe sex={sex!r}")
            return

        dir_path = Path(dir_str.strip() or ".").resolve()
        if not dir_path.is_dir():
            messagebox.showerror("MSC – Puchar", f"Folder MSC nie istnieje:\n{dir_path}")
            return

        season = dir_path.parent.name if dir_path.parent.name else "S45"

        groups_ranked: dict[tuple[str, int], dict] = {}
        missing: list[str] = []

        # wczytanie i posortowanie grup A–D
        for g in ("A", "B", "C", "D"):
            fname = f"{season}_MSC_{sex}_Grupa_{g}.csv"
            p = dir_path / fname
            if not p.is_file():
                missing.append(str(p))
                continue

            df = None
            try:
                # próbujemy tym samym helperem co w CC
                df = _cc_read_q_csv_any(p)
            except Exception:
                df = None

            if df is None:
                for enc in ("cp1250", "utf-8-sig", "latin-1"):
                    try:
                        df = pd.read_csv(p, sep=";", encoding=enc)
                        break
                    except Exception:
                        df = None

            if df is None or df.empty:
                missing.append(str(p))
                continue

            ranked = _cc_rank_group(df)
            for _, r in ranked.iterrows():
                try:
                    pos = int(r.get("Pozycja", 0) or 0)
                except Exception:
                    pos = 0
                if pos <= 0:
                    continue
                team = str(r.get("Drużyna", "") or "").strip()
                nat = str(r.get("Kraj", "") or "").strip()
                if not team or not nat:
                    continue
                groups_ranked[(g, pos)] = {"Drużyna": team, "Kraj": nat}

        if not groups_ranked:
            messagebox.showerror(
                "MSC – Puchar",
                "Brak kompletnych tabel grup MSC.\nSprawdź pliki z grupami."
            )
            return

        def _team_from_group(g: str, pos: int) -> tuple[str, str]:
            row = groups_ranked.get((g, pos))
            if row:
                return row["Drużyna"], row["Kraj"]
            return "", ""

        matches: list[dict] = []

        def _add_match(mecz_id: str, faza: str, g1=None, g2=None):
            t1, n1 = ("", "")
            t2, n2 = ("", "")
            if g1 is not None:
                t1, n1 = _team_from_group(*g1)
            if g2 is not None:
                t2, n2 = _team_from_group(*g2)

            matches.append({
                "Mecz": mecz_id,
                "Faza": faza,
                "Drużyna1": t1,
                "Kraj1": n1,
                "Punkty1": 0,
                "Minipunkty1": 0,
                "Drużyna2": t2,
                "Kraj2": n2,
                "Punkty2": 0,
                "Minipunkty2": 0,
            })

        # 1/4 finału (1–8) – identycznie jak w CC, tylko MSC
        _add_match("M1",  "1/4 finału (1–8)", ("A", 1), ("B", 2))
        _add_match("M2",  "1/4 finału (1–8)", ("B", 1), ("C", 2))
        _add_match("M3",  "1/4 finału (1–8)", ("C", 1), ("D", 2))
        _add_match("M4",  "1/4 finału (1–8)", ("D", 1), ("A", 2))

        # 1–4: półfinały + finał + mecz o 3. miejsce (uzupełniane później z wyników)
        _add_match("M5",  "1/2 finału (1–4)")
        _add_match("M6",  "1/2 finału (1–4)")
        _add_match("M7",  "Mecz o 1. miejsce")
        _add_match("M8",  "Mecz o 3. miejsce")

        # 5–8
        _add_match("M9",  "1/2 finału (5–8)")
        _add_match("M10", "1/2 finału (5–8)")
        _add_match("M11", "Mecz o 5. miejsce")
        _add_match("M12", "Mecz o 7. miejsce")

        # 9–12: 3. miejsca w grupach
        _add_match("M13", "1/2 finału (9–12)", ("A", 3), ("D", 3))
        _add_match("M14", "1/2 finału (9–12)", ("B", 3), ("C", 3))
        _add_match("M15", "Mecz o 9. miejsce")
        _add_match("M16", "Mecz o 11. miejsce")

        # 13–16: 4. miejsca w grupach
        _add_match("M17", "1/2 finału (13–16)", ("A", 4), ("D", 4))
        _add_match("M18", "1/2 finału (13–16)", ("B", 4), ("C", 4))
        _add_match("M19", "Mecz o 13. miejsce")
        _add_match("M20", "Mecz o 15. miejsce")

        df_out = pd.DataFrame(matches)
        out_path = dir_path / f"{season}_MSC_{sex}_Puchar.csv"

        try:
            df_out.to_csv(out_path, sep=";", encoding="cp1250", index=False)
        except Exception:
            df_out.to_csv(out_path, sep=";", encoding="utf-8-sig", index=False)

        msg = f"Ułożono fazę pucharową MSC-{sex}.\nZapisano do:\n{out_path}"
        if missing:
            msg += "\n\nBrakujące / problematyczne pliki:\n- " + "\n- ".join(missing)
        messagebox.showinfo("MSC – Puchar", msg)

        try:
            _msc_cup_reload(sex)
        except Exception:
            pass

    def _msc_cup_apply_results(dir_str: str, sex: str):
        """
        Aktualizuje drabinkę MSC na podstawie wyników w pliku
        <sezon>_MSC_<sex>_Puchar.csv (logika zwycięzców jak w CC:
        najpierw Punkty, przy remisie Minipunkty).
        """
        from tkinter import messagebox
        from pathlib import Path
        import pandas as pd

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            messagebox.showerror("MSC – Puchar", f"Nieprawidłowe sex={sex!r}")
            return

        dir_path = Path(dir_str.strip() or ".").resolve()
        season = dir_path.parent.name if dir_path.parent.name else "S45"
        p = dir_path / f"{season}_MSC_{sex}_Puchar.csv"
        if not p.is_file():
            messagebox.showerror("MSC – Puchar", f"Brak pliku drabinki:\n{p}")
            return

        df = None
        for enc in ("cp1250", "utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(p, sep=";", encoding=enc)
                break
            except Exception:
                df = None

        if df is None:
            messagebox.showerror("MSC – Puchar", f"Nie udało się wczytać pliku:\n{p}")
            return

        needed = [
            "Mecz", "Faza",
            "Drużyna1", "Kraj1", "Punkty1", "Minipunkty1",
            "Drużyna2", "Kraj2", "Punkty2", "Minipunkty2",
        ]
        for col in needed:
            if col not in df.columns:
                df[col] = ""

        def _row_for(mcode: str):
            mask = df["Mecz"].astype(str).str.strip().str.upper() == mcode
            if not mask.any():
                return None, None
            idx = df.index[mask][0]
            return idx, df.loc[idx]

        def _num(x):
            try:
                if x is None or x == "":
                    return None
                return float(x)
            except Exception:
                return None

        winners: dict[str, tuple[str, str]] = {}
        losers: dict[str, tuple[str, str]] = {}

        # wyznacz zwycięzców i przegranych dla M1–M20
        for i in range(1, 21):
            mcode = f"M{i}"
            idx, row = _row_for(mcode)
            if row is None:
                continue

            p1 = _num(row.get("Punkty1"))
            p2 = _num(row.get("Punkty2"))
            if (p1 is None or p2 is None) or (p1 == 0 and p2 == 0):
                continue

            if p1 > p2:
                w_side, l_side = "1", "2"
            elif p2 > p1:
                w_side, l_side = "2", "1"
            else:
                m1 = _num(row.get("Minipunkty1"))
                m2 = _num(row.get("Minipunkty2"))
                if m1 is None or m2 is None or m1 == m2:
                    continue
                if m1 > m2:
                    w_side, l_side = "1", "2"
                else:
                    w_side, l_side = "2", "1"

            t_w = str(row.get(f"Drużyna{w_side}", "") or "")
            n_w = str(row.get(f"Kraj{w_side}", "") or "")
            t_l = str(row.get(f"Drużyna{l_side}", "") or "")
            n_l = str(row.get(f"Kraj{l_side}", "") or "")
            if not t_w or not n_w or not t_l or not n_l:
                continue

            winners[mcode] = (t_w, n_w)
            losers[mcode] = (t_l, n_l)

        # zależności między meczami – identyczne jak w CC
        deps: dict[str, list[tuple[str, str, str]]] = {
            # 1–4
            "M5":  [("1", "M1", "W"), ("2", "M2", "W")],
            "M6":  [("1", "M3", "W"), ("2", "M4", "W")],
            "M7":  [("1", "M5", "W"), ("2", "M6", "W")],
            "M8":  [("1", "M5", "L"), ("2", "M6", "L")],
            # 5–8
            "M9":  [("1", "M1", "L"), ("2", "M2", "L")],
            "M10": [("1", "M3", "L"), ("2", "M4", "L")],
            "M11": [("1", "M9", "W"), ("2", "M10", "W")],
            "M12": [("1", "M9", "L"), ("2", "M10", "L")],
            # 9–12
            "M15": [("1", "M13", "W"), ("2", "M14", "W")],
            "M16": [("1", "M13", "L"), ("2", "M14", "L")],
            # 13–16
            "M19": [("1", "M17", "W"), ("2", "M18", "W")],
            "M20": [("1", "M17", "L"), ("2", "M18", "L")],
        }

        changed = False

        for target, deps_list in deps.items():
            tidx, trow = _row_for(target)
            if trow is None:
                continue
            for slot, src_code, src_kind in deps_list:
                src_dict = winners if src_kind == "W" else losers
                if src_code not in src_dict:
                    continue
                team, nat = src_dict[src_code]
                col_team = f"Drużyna{slot}"
                col_nat = f"Kraj{slot}"
                if df.at[tidx, col_team] != team or df.at[tidx, col_nat] != nat:
                    df.at[tidx, col_team] = team
                    df.at[tidx, col_nat] = nat
                    changed = True

        if changed:
            try:
                df.to_csv(p, sep=";", encoding="cp1250", index=False)
            except Exception:
                df.to_csv(p, sep=";", encoding="utf-8-sig", index=False)

            messagebox.showinfo(
                "MSC – Puchar",
                "Zaktualizowano drabinkę MSC na podstawie wyników meczów.",
            )

            try:
                _msc_cup_reload(sex)
            except Exception:
                pass
        else:
            messagebox.showinfo(
                "MSC – Puchar",
                "Brak zmian w drabince MSC (nie znaleziono nowych zwycięzców).",
            )

    def _build_msc_cup_tab(parent, sex: str):
        """Zakładka 'Puchar' dla MSC-MEN / MSC-WOMEN – canvas jak w CC."""
        from tkinter import ttk
        import tkinter as tk
        nonlocal msc_cup_canvas

        sex = str(sex or "").upper()[:1]

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 4))

        def _dir_for_sex(s: str) -> str:
            return (self.msc_m_dir_var if s == "M" else self.msc_w_dir_var).get().strip()

        ttk.Button(
            top,
            text="Poukładaj fazę pucharową",
            command=lambda s=sex: _msc_build_cup_from_groups(_dir_for_sex(s), s),
        ).pack(side="left")

        ttk.Button(
            top,
            text="Uaktualnij drabinkę z wyników",
            command=lambda s=sex: _msc_cup_apply_results(_dir_for_sex(s), s),
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            top,
            text="Odśwież z pliku",
            command=lambda s=sex: _msc_cup_reload(s),
        ).pack(side="right")

        # część z Canvasem (kopiuj-wklej z CC, tylko osobno dla MEN/WOMEN)
        frame_canvas = ttk.Frame(frame)
        frame_canvas.pack(fill="both", expand=True)

        canvas = tk.Canvas(frame_canvas, background="white")
        vscroll = ttk.Scrollbar(frame_canvas, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        frame_canvas.rowconfigure(0, weight=1)
        frame_canvas.columnconfigure(0, weight=1)

        def _on_msc_cup_mousewheel(event):
            # Windows / macOS
            if hasattr(event, "delta") and event.delta != 0:
                step = -1 if event.delta > 0 else 1
            else:
                # Linux (Button-4 / Button-5)
                if getattr(event, "num", None) == 4:
                    step = -1
                elif getattr(event, "num", None) == 5:
                    step = 1
                else:
                    step = 0
            if step:
                canvas.yview_scroll(step, "units")
            return "break"

        canvas.bind("<MouseWheel>", _on_msc_cup_mousewheel)
        canvas.bind("<Button-4>", _on_msc_cup_mousewheel)
        canvas.bind("<Button-5>", _on_msc_cup_mousewheel)

        # zapamiętaj canvas dla danej płci
        msc_cup_canvas[sex] = canvas

        # spróbuj od razu wczytać istniejący puchar
        try:
            _msc_cup_reload(sex)
        except Exception as e:
            print("[MSC-Puchar] błąd przy automatycznym odświeżeniu:", e)

        return frame

    def _msc_classif_recompute_and_redraw(sex: str):
        """
        Liczy klasyfikację MSC (Q + Puchar + Finanse) i rysuje ją na canvasie.
        """
        import pandas as _pd
        from pathlib import Path

        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            return

        # folder MSC z GUI
        dir_var = self.msc_m_dir_var if sex == "M" else self.msc_w_dir_var
        root = Path(dir_var.get().strip() or ".").resolve()

        # wylicz DataFrame z klasyfikacją
        try:
            df = _msc_classif_compute_df(root, sex)
        except Exception as e:
            print("[MSC-Klasa] błąd przy liczeniu klasyfikacji:", e)
            df = _pd.DataFrame(columns=["Lp.", "Drużyna", "Kraj", "Punkty",
                                        "Finanse (miejsce)", "Finanse (suma)"])

        _msc_classif_redraw_canvas(sex, df)

    def _msc_classif_compute_df(root_dir, sex: str):
        """
        Zwraca klasyfikację MSC jako DataFrame:
        Lp., Drużyna, Kraj, Punkty, Finanse (miejsce), Finanse (suma)
        """
        import pandas as _pd
        from pathlib import Path

        root_dir = Path(root_dir or ".")
        sex = str(sex or "").upper()[:1]

        # --- 1) Punkty z Q ---
        try:
            df_q = _msc_q_summary_from_dir(root_dir, sex)
        except Exception as e:
            print("[MSC-Klasa] problem z Q:", e)
            df_q = _pd.DataFrame(columns=["Lp.", "Drużyna", "Kraj", "Punkty"])

        if df_q is None or df_q.empty:
            df_q = _pd.DataFrame(columns=["Drużyna", "Kraj", "Punkty"])
        else:
            df_q = df_q[["Drużyna", "Kraj", "Punkty"]].copy()
        df_q.rename(columns={"Punkty": "Pkt_Q"}, inplace=True)

        # --- 2) Punkty z Pucharu MSC ---
        season = root_dir.parent.name or "S45"
        cup_path = root_dir / f"{season}_MSC_{sex}_Puchar.csv"

        cup_parts = []
        if cup_path.is_file():
            try:
                for enc in ("cp1250", "utf-8-sig", "latin-1"):
                    try:
                        df_c = _pd.read_csv(cup_path, sep=";", encoding=enc)
                        break
                    except Exception:
                        df_c = None
                if df_c is not None:
                    for side in (1, 2):
                        tcol = f"Drużyna{side}"
                        kcol = f"Kraj{side}"
                        pcol = f"Punkty{side}"
                        if tcol in df_c.columns and kcol in df_c.columns and pcol in df_c.columns:
                            part = df_c[[tcol, kcol, pcol]].copy()
                            part.rename(columns={tcol: "Drużyna", kcol: "Kraj", pcol: "Punkty"}, inplace=True)
                            cup_parts.append(part)
            except Exception as e:
                print("[MSC-Klasa] problem z wczytaniem pucharu:", e)

        if cup_parts:
            df_cup = _pd.concat(cup_parts, ignore_index=True)
            df_cup["Punkty"] = _pd.to_numeric(df_cup["Punkty"], errors="coerce").fillna(0.0)
            df_cup = df_cup.groupby(["Drużyna", "Kraj"])["Punkty"].sum().reset_index()
            df_cup.rename(columns={"Punkty": "Pkt_Puchar"}, inplace=True)
        else:
            df_cup = _pd.DataFrame(columns=["Drużyna", "Kraj", "Pkt_Puchar"])

        # --- 3) Scalenie Q + Puchar ---
        if df_q.empty and df_cup.empty:
            return _pd.DataFrame(columns=["Lp.", "Drużyna", "Kraj", "Punkty",
                                          "Finanse (miejsce)", "Finanse (suma)"])

        df = _pd.merge(df_q, df_cup, on=["Drużyna", "Kraj"], how="outer")
        df["Pkt_Q"] = _pd.to_numeric(df.get("Pkt_Q", 0.0), errors="coerce").fillna(0.0)
        df["Pkt_Puchar"] = _pd.to_numeric(df.get("Pkt_Puchar", 0.0), errors="coerce").fillna(0.0)
        df["Punkty"] = df["Pkt_Q"] + df["Pkt_Puchar"]

        df = df.sort_values("Punkty", ascending=False).reset_index(drop=True)
        df.insert(0, "Lp.", range(1, len(df) + 1))

        # --- 4) Finanse (miejsce) + Finanse (suma) ---
        # ta sama tabelka co w CC:
        # 1: 600k, 2: 500k, 3: 400k, 4: 300k, 5: 250k, 6: 200k, reszta 0
        prize_map = {
            1: 600_000,
            2: 500_000,
            3: 400_000,
            4: 300_000,
            5: 250_000,
            6: 200_000,
        }

        fin_place = []
        fin_sum = []
        for i, _r in df.iterrows():
            place = int(_r["Lp."])
            money = prize_map.get(place, 0)
            fin_place.append(money)
            # dla pojedynczego MSC Finanse (suma) = Finanse (miejsce)
            fin_sum.append(money)

        df["Finanse (miejsce)"] = fin_place
        df["Finanse (suma)"] = fin_sum

        return df

    def _cc_draw_groups_for_dir(dir_str: str):
        """
        Losuje grupy A–D z TOP16 z kwalifikacji CC i zapisuje:
        S45_CC_Grupa_A.csv ... S45_CC_Grupa_D.csv
        w wybranym folderze.
        """
        from tkinter import messagebox

        dir_path = Path(dir_str.strip() or ".")
        if not dir_path.is_dir():
            messagebox.showerror("CC – grupy", f"Folder CC nie istnieje:\n{dir_path}")
            return

        try:
            df_q = _cc_q_summary_from_dir(dir_path)
        except Exception as e:
            messagebox.showerror("CC – grupy", f"Problem z wczytaniem kwalifikacji CC:\n{e}")
            return

        if df_q.empty or len(df_q) < 16:
            messagebox.showerror(
                "CC – grupy",
                f"Za mało drużyn w kwalifikacjach CC (mam {len(df_q)}, potrzebuję ≥16).",
            )
            return

        top16 = df_q.head(16).copy().reset_index(drop=True)

        # koszyki wg Lp.: 1–4, 5–8, 9–12, 13–16
        basket_ids = []
        for idx in range(len(top16)):
            lp = idx + 1
            if lp <= 4:
                basket_ids.append(1)
            elif lp <= 8:
                basket_ids.append(2)
            elif lp <= 12:
                basket_ids.append(3)
            else:
                basket_ids.append(4)
        top16["Koszyk"] = basket_ids

        rng = np.random.default_rng()
        group_labels = ["A", "B", "C", "D"]
        groups: dict[str, list[dict]] = {g: [] for g in group_labels}

        # z każdego koszyka losowo rozkładamy po 1 drużynie do każdej grupy
        for b in (1, 2, 3, 4):
            pool = top16[top16["Koszyk"] == b].index.to_list()
            if len(pool) < 4:
                # paranoja, ale jakbyś miał mniej drużyn – niech się wysypie głośno
                messagebox.showerror(
                    "CC – grupy",
                    f"Koszyk {b} ma tylko {len(pool)} drużyny. Sprawdź kwalifikacje CC.",
                )
                return
            rng.shuffle(pool)
            for g_idx, g in enumerate(group_labels):
                idx = pool[g_idx]
                row = top16.loc[idx]
                groups[g].append({
                    "Drużyna": row["Drużyna"],
                    "Kraj": row["Kraj"],
                })

        # zapis czterech plików: Lp., Drużyna, Kraj, Punkty Zdobyte, Punkty Stracone, Minipunkty
        for g in group_labels:
            recs = []
            for lp, row in enumerate(groups[g], start=1):
                recs.append({
                    "Lp.": lp,
                    "Drużyna": row["Drużyna"],
                    "Kraj": row["Kraj"],
                    "Punkty Zdobyte": 0,
                    "Punkty Stracone": 0,
                    "Minipunkty": 0,
                })
            df_g = pd.DataFrame(recs, columns=["Lp.", "Drużyna", "Kraj", "Punkty Zdobyte", "Punkty Stracone", "Minipunkty"])
            out_path = dir_path / f"S45_CC_Grupa_{g}.csv"
            try:
                df_g.to_csv(out_path, sep=";", encoding="cp1250", index=False)
            except Exception:
                # jak coś nie zagra z cp1250, spróbuj utf-8-sig
                df_g.to_csv(out_path, sep=";", encoding="utf-8-sig", index=False)

        messagebox.showinfo(
            "CC – grupy",
            "Wylosowano grupy CC i zapisano:\n"
            "S45_CC_Grupa_A.csv … S45_CC_Grupa_D.csv",
        )

    def _cc_collect_groups():
        """
        Zbiera skład grup CC z tabelek FrozenTable.

        Zwraca:
            { "A": [(team, nat), ...], "B": [...], ... }
        """
        groups: dict[str, list[tuple[str, str]]] = {}
        for g, ft in cc_groups.items():
            rows: list[tuple[str, str]] = []
            try:
                tv = ft.tvR
            except Exception:
                continue
            for iid in tv.get_children(""):
                item = tv.item(iid)
                team = str(item.get("text", "")).strip()
                vals = item.get("values", ())
                nat = str(vals[0]).strip() if vals else ""
                if team and nat:
                    rows.append((team, nat))
            if rows:
                groups[g] = rows
        return groups

    def _cc_build_group_schedule(groups: dict[str, list[tuple[str, str]]]):
        """
        Buduje terminarz dla grup CC.
        Zakładamy 4 drużyny w grupie, 3 kolejki, bez rewanżów.
        """
        schedule: list[dict] = []
        for g in sorted(groups.keys()):
            teams = groups[g]
            if len(teams) < 4:
                # nic nie robimy, jeśli grupa niepełna
                continue
            # bierzemy pierwsze 4 drużyny
            (t1, n1), (t2, n2), (t3, n3), (t4, n4) = teams[:4]

            match_no = 1

            def _add_round(kolejka: int, ta: str, na: str, tb: str, nb: str):
                nonlocal match_no
                schedule.append(
                    {
                        "Kolejka": kolejka,
                        "Grupa": g,
                        "Mecz": match_no,
                        "Drużyna1": ta,
                        "Kraj1": na,
                        "Drużyna2": tb,
                        "Kraj2": nb,
                    }
                )
                match_no += 1

            # klasyczny układ dla 4-zespołowej grupy
            # Kolejka 1
            _add_round(1, t1, n1, t4, n4)
            _add_round(1, t2, n2, t3, n3)
            # Kolejka 2
            _add_round(2, t4, n4, t3, n3)
            _add_round(2, t1, n1, t2, n2)
            # Kolejka 3
            _add_round(3, t1, n1, t3, n3)
            _add_round(3, t2, n2, t4, n4)

        # sortujemy po kolejce, grupie, meczu
        schedule.sort(key=lambda r: (r["Kolejka"], r["Grupa"], r["Mecz"]))
        return schedule

    def _cc_schedule_reload():
        """
        Odświeża tabelę terminarza na podstawie aktualnych grup.
        """
        if tv_cc_schedule is None:
            return

        groups = _cc_collect_groups()
        schedule_list = _cc_build_group_schedule(groups)

        tv = tv_cc_schedule
        tv.delete(*tv.get_children(""))
        for row in schedule_list:
            tv.insert(
                "",
                "end",
                values=(
                    row["Kolejka"],
                    row["Grupa"],
                    row["Mecz"],
                    row["Drużyna1"],
                    row["Kraj1"],
                    row["Drużyna2"],
                    row["Kraj2"],
                ),
            )    

    def _cc_groups_reload():
        """Wczytuje S45_CC_Grupa_A…D.csv z folderu CC i odświeża tabelki."""
        dir_path = Path(cc_dir_var.get().strip() or ".")
        cols = ["Lp.", "Drużyna", "Kraj", "Punkty Zdobyte", "Punkty Stracone", "Minipunkty"]

        for g, ft in cc_groups.items():
            # wyczyść tabelę
            ft.clear()

            p = dir_path / f"S45_CC_Grupa_{g}.csv"
            if not p.is_file():
                continue

            try:
                df = _cc_read_q_csv_any(p)
            except Exception as e:
                print("DEBUG CC grupy:", p, "->", e)
                continue

            # dopilnuj kolumn
            for col in cols:
                if col not in df.columns:
                    if col in ("Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
                        df[col] = 0
                    else:
                        df[col] = ""
            df = df[cols]

            for _, r in df.iterrows():
                ft.insert_row(dict(r))

        # po odświeżeniu grup spróbuj automatycznie zbudować terminarz
        try:
            _cc_schedule_reload()
        except Exception:
            pass

    def _cc_q_reload():
        """
        Czyta:
          S45/Team S45/S45_Q_CC_M.csv
          S45/Team S45/S45_Q_CC_W.csv
          S45/Team S45/S45_Q_CC_X.csv
        i buduje tabelę:
          Lp., Drużyna, Kraj, MEN, WOMEN, MIX, Suma
        """
        import pandas as _pd
        from tkinter import messagebox

        dir_path = Path(cc_dir_var.get().strip() or ".")
        problems = []
        data = {}  # (Drużyna,Kraj) -> dict

        def _load_one(suffix: str, col_name: str):
            fname = f"S45_Q_CC_{suffix}.csv"
            p = dir_path / fname
            if not p.exists():
                # fallback: glob po wzorcu (obsługuje np. S45_Q_CC_M_wyniki.csv)
                candidates = sorted(dir_path.glob(f"*_Q_CC_{suffix}*.csv"))
                if candidates:
                    p = candidates[0]
                else:
                    problems.append(f"Brak pliku: {dir_path / fname}")
                    return

            df = None
            last_err = None
            # bezpieczne wczytanie (różne kodowania / separatory)
            for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
                try:
                    df = _pd.read_csv(p, sep=None, engine="python", encoding=enc)
                    break
                except Exception as e:
                    last_err = e
                    df = None
            if df is None:
                try:
                    df = _pd.read_csv(p, sep=";", encoding="utf-8-sig")
                except Exception:
                    problems.append(f"Nie mogę wczytać: {p}\n{last_err}")
                    return

            # normalizacja nagłówków: Lp.;Drużyna;Kraj;Punkty
            ren = {}
            for c in df.columns:
                lc = str(c).strip().lower()
                if lc in {"lp", "lp."}:
                    ren[c] = "Lp."
                elif "drużyna" in lc or "druzyna" in lc:
                    ren[c] = "Drużyna"
                elif lc in {"kraj", "nat"}:
                    ren[c] = "Kraj"
                elif lc.startswith("punkty") or lc.startswith("pkt") or lc == "suma":
                    ren[c] = "Punkty"
            if ren:
                df = df.rename(columns=ren)

            # jesli brak Punkty — spróbuj pierwszą kolumnę liczbową
            if "Punkty" not in df.columns:
                for c in df.columns:
                    if c not in ("Drużyna", "Kraj", "Lp."):
                        test = _pd.to_numeric(
                            df[c].astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                            errors="coerce"
                        )
                        if test.notna().sum() > 0:
                            df = df.rename(columns={c: "Punkty"})
                            break

            for col in ("Drużyna", "Kraj", "Punkty"):
                if col not in df.columns:
                    problems.append(f"Plik {p} nie ma kolumny '{col}'")
                    return

            for _, r in df.iterrows():
                team = str(r.get("Drużyna", "") or "").strip()
                nat  = str(r.get("Kraj", "") or "").strip()
                if not team and not nat:
                    continue
                key = (team, nat)
                if key not in data:
                    data[key] = {"Drużyna": team, "Kraj": nat, "MEN": 0.0, "WOMEN": 0.0, "MIX": 0.0}
                import re as _re2
                raw_pts = str(r.get("Punkty", 0.0) or "0").strip()
                raw_pts = _re2.sub(r"[^\d.\-]", "", raw_pts)
                pts = _pd.to_numeric(raw_pts, errors="coerce")
                if _pd.isna(pts):
                    pts = 0.0
                data[key][col_name] += float(pts)

        # wczytaj M/W/X
        _load_one("M", "MEN")
        _load_one("W", "WOMEN")
        _load_one("X", "MIX")

        # zbuduj DF wynikowy
        rows = []
        for (team, nat), vals in data.items():
            men = float(vals.get("MEN", 0.0))
            wom = float(vals.get("WOMEN", 0.0))
            mix = float(vals.get("MIX", 0.0))
            suma = round(men + wom + mix, 1)   # <= zaokrąglenie do 1 miejsca

            rows.append({
                "Drużyna": team,
                "Kraj": nat,
                "MEN": men,
                "WOMEN": wom,
                "MIX": mix,
                "Suma": suma,
            })

        if rows:
            df_out = _pd.DataFrame(rows)
            df_out = df_out.sort_values(["Suma", "Drużyna"], ascending=[False, True]).reset_index(drop=True)
            df_out.insert(0, "Lp.", range(1, len(df_out) + 1))
        else:
            df_out = _pd.DataFrame(columns=cols_cc)

        # Obiekt FrozenTable sam wyczyści dane, dopasuje flagi i wstawi wiersze
        tv_cc_q.set_dataframe(df_out)
        try:
            tv_cc_q.autosize()
        except Exception:
            pass

        try:
            safe_autosize_columns(tv_cc_q)
        except Exception:
            pass

        if problems:
            messagebox.showwarning("CC – Q", "\n".join(dict.fromkeys(problems)))

    def _cc_cup_redraw_canvas(df):
        """Rysuje mecze CC Cup na canvasie z flagami obu drużyn."""
        nonlocal cc_cup_canvas
        if cc_cup_canvas is None:
            return

        c = cc_cup_canvas
        c.delete("all")
        c.img_refs = []   # żeby GC nie zjadł flag

        margin_x = 20
        margin_y = 20
        row_h = 80
        box_w = 900

        for i, row in df.iterrows():
            mecz   = str(row.get("Mecz", "")).strip()
            faza   = str(row.get("Faza", "")).strip()
            d1     = str(row.get("Drużyna1", "")).strip()
            nat1   = str(row.get("Kraj1", "")).strip()
            d2     = str(row.get("Drużyna2", "")).strip()
            nat2   = str(row.get("Kraj2", "")).strip()
            p1     = row.get("Punkty1", "")
            p2     = row.get("Punkty2", "")

            y0 = margin_y + i * row_h
            y1 = y0 + row_h - 10

            # czy to mecz o 1/3/5/... miejsce?
            bg_fill = "#f0f0f0"
            try:
                low_faza = faza.lower()
                if "miejsce" in low_faza:
                    import re
                    mnum = re.search(r"(\d+)", low_faza)
                    if mnum:
                        place = int(mnum.group(1))
                        if place % 2 == 1:  # 1, 3, 5, 7...
                            bg_fill = "#ceab20"  # delikatne żółtawe tło
            except Exception:
                pass

            # tło meczu
            c.create_rectangle(
                margin_x, y0,
                margin_x + box_w, y1,
                outline="#555555",
                width=1,
                fill=bg_fill
            )

            # flagi
            img1 = _flag_cached(nat1) if nat1 else None
            img2 = _flag_cached(nat2) if nat2 else None
            if img1:
                c.img_refs.append(img1)
            if img2:
                c.img_refs.append(img2)

            cy = (y0 + y1) // 2 - 8  # środek pionowo

            # LEWA STRONA – Drużyna1 + flaga
            x = margin_x + 10
            if img1:
                c.create_image(x, cy, image=img1, anchor="w")
                x += 26  # szerokość flagi + odstęp

            c.create_text(
                x, cy,
                text=d1,
                anchor="w",
                font=("TkDefaultFont", 10, "bold")
            )

            # wynik 1
            c.create_text(
                margin_x + 260, cy,
                text=str(p1) if p1 != "" else "",
                anchor="e",
                font=("TkDefaultFont", 10)
            )

            # dwukropek
            c.create_text(
                margin_x + 280, cy,
                text=":",
                anchor="center",
                font=("TkDefaultFont", 10, "bold")
            )

            # wynik 2
            c.create_text(
                margin_x + 300, cy,
                text=str(p2) if p2 != "" else "",
                anchor="w",
                font=("TkDefaultFont", 10)
            )

            # PRAWA STRONA – Drużyna2 + flaga
            x2 = margin_x + 500
            # najpierw tekst, żeby było symetryczniej
            c.create_text(
                x2, cy,
                text=d2,
                anchor="e",
                font=("TkDefaultFont", 10, "bold")
            )
            x2 += 6
            if img2:
                c.create_image(x2, cy, image=img2, anchor="w")

            # opis fazy + numer meczu na dole
            c.create_text(
                margin_x + 10,
                y1 - 12,
                text=f"{faza} ({mecz})" if faza or mecz else "",
                anchor="w",
                fill="#666666",
                font=("TkDefaultFont", 8)
            )

        # ustaw region przewijania
        bbox = c.bbox("all")
        if bbox:
            c.configure(scrollregion=bbox)

    def _cc_rank_group(df: pd.DataFrame) -> pd.DataFrame:
        """
        Sortuje tabelę grupy wg:
          1) Punkty Zdobyte (DESC)
          2) Minipunkty (DESC)
          3) Punkty Stracone (ASC)
          4) oryginalna kolejność (Lp.)
        Zwraca DF z kolumną 'Pozycja' = 1..N.
        """
        dfx = df.copy()
        for col in ("Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
            if col not in dfx.columns:
                dfx[col] = 0
            dfx[col] = pd.to_numeric(dfx[col], errors="coerce").fillna(0.0)

        # fallback, gdyby Lp. było dziwnie
        dfx["__orig"] = np.arange(len(dfx))

        dfx = dfx.sort_values(
            by=["Punkty Zdobyte", "Minipunkty", "Punkty Stracone", "__orig"],
            ascending=[False, False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)

        dfx["Pozycja"] = np.arange(1, len(dfx) + 1)
        return dfx

    def _cc_build_cup_from_groups(dir_str: str):
        """
        Buduje drabinkę pucharową 1–16 na podstawie plików:
          S45_CC_Grupa_A…D.csv

        Struktura:
          M1:  1A – 2B   (QF)
          M2:  1B – 2C
          M3:  1C – 2D
          M4:  1D – 2A

          M5:  Zw. M1 – Zw. M2   (SF 1–4)
          M6:  Zw. M3 – Zw. M4

          M7:  Zw. M5 – Zw. M6   (Finał 1–2)
          M8:  Prz. M5 – Prz. M6 (3–4)

          M9:  Prz. M1 – Prz. M2 (SF 5–8)
          M10: Prz. M3 – Prz. M4

          M11: Zw. M9 – Zw. M10  (5–6)
          M12: Prz. M9 – Prz. M10 (7–8)

          M13: 3A – 3D           (SF 9–12)
          M14: 3B – 3C
          M15: Zw. M13 – Zw. M14 (9–10)
          M16: Prz. M13 – Prz. M14 (11–12)

          M17: 4A – 4D           (SF 13–16)
          M18: 4B – 4C
          M19: Zw. M17 – Zw. M18 (13–14)
          M20: Prz. M17 – Prz. M18 (15–16)
        """
        from tkinter import messagebox

        dir_path = Path(dir_str.strip() or ".")
        if not dir_path.is_dir():
            messagebox.showerror("CC – Puchar", f"Folder CC nie istnieje:\n{dir_path}")
            return

        groups_ranked: dict[tuple[str, int], dict] = {}
        missing = []

        for g in ("A", "B", "C", "D"):
            p = dir_path / f"S45_CC_Grupa_{g}.csv"
            if not p.is_file():
                missing.append(str(p))
                continue
            try:
                df_raw = _cc_read_q_csv_any(p)
            except Exception as e:
                messagebox.showerror("CC – Puchar", f"Problem z wczytaniem {p}:\n{e}")
                return

            for col in ("Lp.", "Drużyna", "Kraj", "Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
                if col not in df_raw.columns:
                    if col in ("Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
                        df_raw[col] = 0
                    else:
                        df_raw[col] = ""

            df_g = df_raw[["Lp.", "Drużyna", "Kraj", "Punkty Zdobyte", "Punkty Stracone", "Minipunkty"]]
            df_g = _cc_rank_group(df_g)

            if len(df_g) < 4:
                messagebox.showerror("CC – Puchar", f"Grupa {g} ma mniej niż 4 drużyny.")
                return

            for _, r in df_g.iterrows():
                pos = int(r.get("Pozycja", 0) or 0)
                if pos < 1 or pos > 4:
                    continue
                key = (g, pos)
                groups_ranked[key] = {
                    "Drużyna": str(r.get("Drużyna", "") or ""),
                    "Kraj": str(r.get("Kraj", "") or "").strip().upper(),
                }

        if missing:
            msg = "Brakuje plików grup:\n" + "\n".join(missing)
            messagebox.showerror("CC – Puchar", msg)
            return

        def _from_group(gr: str, pos: int) -> tuple[str, str]:
            info = groups_ranked.get((gr, pos), {})
            return (
                str(info.get("Drużyna", "") or ""),
                str(info.get("Kraj", "") or ""),
            )

        matches = []

        def _add_match(code: str, faza: str,
                       g1: tuple[str, int] | None = None,
                       g2: tuple[str, int] | None = None):
            if g1 is not None:
                t1, n1 = _from_group(*g1)
            else:
                t1, n1 = "", ""
            if g2 is not None:
                t2, n2 = _from_group(*g2)
            else:
                t2, n2 = "", ""

            matches.append({
                "Mecz": code,
                "Faza": faza,
                "Drużyna1": t1,
                "Kraj1": n1,
                "Punkty1": 0,
                "Minipunkty1": 0,
                "Drużyna2": t2,
                "Kraj2": n2,
                "Punkty2": 0,
                "Minipunkty2": 0,
            })

        # 1/4 finału (1–8)
        _add_match("M1",  "1/4 finału",         ("A", 1), ("B", 2))
        _add_match("M2",  "1/4 finału",         ("B", 1), ("C", 2))
        _add_match("M3",  "1/4 finału",         ("C", 1), ("D", 2))
        _add_match("M4",  "1/4 finału",         ("D", 1), ("A", 2))

        # 1/2 finału 1–4
        _add_match("M5",  "1/2 finału (1–4)")
        _add_match("M6",  "1/2 finału (1–4)")

        # Finał + mecz o 3. miejsce
        _add_match("M7",  "Mecz o 1. miejsce")
        _add_match("M8",  "Mecz o 3. miejsce")

        # 1/2 finału 5–8
        _add_match("M9",  "1/2 finału (5–8)")
        _add_match("M10", "1/2 finału (5–8)")

        # mecze o 5. i 7. miejsce
        _add_match("M11", "Mecz o 5. miejsce")
        _add_match("M12", "Mecz o 7. miejsce")

        # 9–12: 3. miejsca w grupach
        _add_match("M13", "1/2 finału (9–12)",  ("A", 3), ("D", 3))
        _add_match("M14", "1/2 finału (9–12)",  ("B", 3), ("C", 3))
        _add_match("M15", "Mecz o 9. miejsce")
        _add_match("M16", "Mecz o 11. miejsce")

        # 13–16: 4. miejsca w grupach
        _add_match("M17", "1/2 finału (13–16)", ("A", 4), ("D", 4))
        _add_match("M18", "1/2 finału (13–16)", ("B", 4), ("C", 4))
        _add_match("M19", "Mecz o 13. miejsce")
        _add_match("M20", "Mecz o 15. miejsce")

        df_cup = pd.DataFrame(matches, columns=[
            "Mecz", "Faza",
            "Drużyna1", "Kraj1", "Punkty1", "Minipunkty1",
            "Drużyna2", "Kraj2", "Punkty2", "Minipunkty2",
        ])

        out_path = dir_path / "S45_CC_Puchar.csv"
        try:
            df_cup.to_csv(out_path, sep=";", encoding="cp1250", index=False)
        except Exception:
            df_cup.to_csv(out_path, sep=";", encoding="utf-8-sig", index=False)

        try:
            _cc_cup_reload()
        except Exception:
            pass

        messagebox.showinfo(
            "CC – Puchar",
            "Ułożono drabinkę pucharową 1–16 i zapisano do:\n"
            f"{out_path}"
        )

    def _cc_cup_reload():
        from pathlib import Path
        import pandas as _pd

        root = Path(cc_dir_var.get().strip() or ".").resolve()

        # znajdź folder sezonu (np. S45) automatycznie
        season = root.parent.name   # da "S45"

        path = root / f"{season}_CC_Puchar.csv"

        if not path.is_file():
            return

        df = _cc_read_q_csv_any(path)  # albo pd.read_csv(..., sep=";") – zależy co już masz

        # ewentualne poprawki kolumn:
        needed = ["Mecz", "Faza", "Drużyna1", "Kraj1", "Punkty1", "Minipunkty1",
                  "Drużyna2", "Kraj2", "Punkty2", "Minipunkty2"]
        for col in needed:
            if col not in df.columns:
                df[col] = ""  # albo 0 dla punktów

        df = df[needed]

        # TU magia:
        _cc_cup_redraw_canvas(df)

    def _cc_pick_winner_loser(row):
        """
        Zwraca ('1','2') jeśli wygrała Drużyna1, przegrała Drużyna2 itd.
        Albo (None, None), jeśli nie da się jednoznacznie ustalić.
        Logika:
          1) wyższe Punkty
          2) przy remisie – wyższe Minipunkty
        """
        import pandas as _pd

        def _num(v):
            x = _pd.to_numeric(v, errors="coerce")
            return float(x) if not _pd.isna(x) else None

        p1 = _num(row.get("Punkty1"))
        p2 = _num(row.get("Punkty2"))

        # brak danych = brak rozstrzygnięcia
        if p1 is None or p2 is None:
            return None, None

        if p1 > p2:
            return "1", "2"
        if p2 > p1:
            return "2", "1"

        # remis -> Minipunkty
        m1 = _num(row.get("Minipunkty1"))
        m2 = _num(row.get("Minipunkty2"))
        if m1 is None or m2 is None:
            return None, None

        if m1 > m2:
            return "1", "2"
        if m2 > m1:
            return "2", "1"

        return None, None

    def _cc_cup_apply_results(dir_str: str):
        """
        Czyta S45_CC_Puchar.csv, wyznacza zwycięzców/przegranych
        i uzupełnia kolejne rundy:
          M5, M6  ← Zw. M1..M4
          M7, M8  ← Zw./Prz. M5..M6
          M9,10   ← Prz. M1..M4
          M11,12  ← Zw./Prz. M9..M10
          M15,16  ← Zw./Prz. M13..M14
          M19,20  ← Zw./Prz. M17..M18
        """
        from tkinter import messagebox

        dir_path = Path(dir_str.strip() or ".")
        p = dir_path / "S45_CC_Puchar.csv"
        if not p.is_file():
            messagebox.showerror(
                "CC – Puchar",
                f"Brak pliku drabinki:\n{p}"
            )
            return

        try:
            df = _cc_read_q_csv_any(p)
        except Exception as e:
            messagebox.showerror("CC – Puchar", f"Problem z wczytaniem {p}:\n{e}")
            return

        # dopilnuj kolumn
        cols = [
            "Mecz", "Faza",
            "Drużyna1", "Kraj1", "Punkty1", "Minipunkty1",
            "Drużyna2", "Kraj2", "Punkty2", "Minipunkty2",
        ]
        for col in cols:
            if col not in df.columns:
                if col.startswith("Punkty") or col.startswith("Minipunkty"):
                    df[col] = 0
                else:
                    df[col] = ""
        df = df[cols]

        # mapa: kod meczu → wiersz (Series)
        def _row_for(mcode: str):
            sub = df[df["Mecz"].astype(str) == mcode]
            if sub.empty:
                return None, None
            idx = sub.index[0]
            return idx, df.loc[idx]

        # policz zwycięzców / przegranych
        winners: dict[str, tuple[str, str]] = {}
        losers: dict[str, tuple[str, str]] = {}

        for mcode in [f"M{i}" for i in range(1, 21)]:
            idx, row = _row_for(mcode)
            if row is None:
                continue
            w_side, l_side = _cc_pick_winner_loser(row)
            if not w_side or not l_side:
                continue
            t_w = str(row.get(f"Drużyna{w_side}", "") or "")
            n_w = str(row.get(f"Kraj{w_side}", "") or "")
            t_l = str(row.get(f"Drużyna{l_side}", "") or "")
            n_l = str(row.get(f"Kraj{l_side}", "") or "")
            winners[mcode] = (t_w, n_w)
            losers[mcode] = (t_l, n_l)

        # zależności drabinki: target → [(slot, source_m, 'W'/'L')]
        deps: dict[str, list[tuple[str, str, str]]] = {
            # 1–4
            "M5":  [("1", "M1", "W"), ("2", "M2", "W")],
            "M6":  [("1", "M3", "W"), ("2", "M4", "W")],
            "M7":  [("1", "M5", "W"), ("2", "M6", "W")],
            "M8":  [("1", "M5", "L"), ("2", "M6", "L")],
            # 5–8
            "M9":  [("1", "M1", "L"), ("2", "M2", "L")],
            "M10": [("1", "M3", "L"), ("2", "M4", "L")],
            "M11": [("1", "M9", "W"), ("2", "M10", "W")],
            "M12": [("1", "M9", "L"), ("2", "M10", "L")],
            # 9–12
            "M15": [("1", "M13", "W"), ("2", "M14", "W")],
            "M16": [("1", "M13", "L"), ("2", "M14", "L")],
            # 13–16
            "M19": [("1", "M17", "W"), ("2", "M18", "W")],
            "M20": [("1", "M17", "L"), ("2", "M18", "L")],
        }

        changed = False

        for target, slots in deps.items():
            tidx, trow = _row_for(target)
            if trow is None:
                continue

            for slot, src_m, kind in slots:
                src_map = winners if kind == "W" else losers
                pair = src_map.get(src_m)
                if not pair:
                    continue
                t_new, n_new = pair
                col_team = f"Drużyna{slot}"
                col_nat  = f"Kraj{slot}"
                col_pts  = f"Punkty{slot}"
                col_mini = f"Minipunkty{slot}"

                t_old = str(trow.get(col_team, "") or "")
                n_old = str(trow.get(col_nat, "") or "")

                if t_old != t_new or n_old != n_new:
                    df.at[tidx, col_team] = t_new
                    df.at[tidx, col_nat]  = n_new
                    # resetuj punkty/minipunkty dla nowej pary
                    df.at[tidx, col_pts]  = 0
                    df.at[tidx, col_mini] = 0
                    changed = True

        if not changed:
            messagebox.showinfo(
                "CC – Puchar",
                "Brak zmian w drabince (brak rozstrzygnięć lub nic się nie zmieniło)."
            )
        else:
            # zapisz z powrotem
            try:
                df.to_csv(p, sep=";", encoding="cp1250", index=False)
            except Exception:
                df.to_csv(p, sep=";", encoding="utf-8-sig", index=False)

            try:
                _cc_cup_reload()
            except Exception:
                pass

            messagebox.showinfo(
                "CC – Puchar",
                "Zaktualizowano drabinkę na podstawie wyników meczów."
            )

        # --- MSC: KLASYFIKACJA KOŃCOWA (Q + Puchar + finanse + ranking) ---

        msc_final_canvas = {"M": None, "W": None}

        def _msc_final_draw(sex: str, df):
            """Rysuje klasyfikację MSC na canvasie (osobno dla M / W)."""
            import math
            sex = (sex or "M").upper()
            c = msc_final_canvas.get(sex)
            if c is None:
                return

            # helper do formatowania pieniędzy
            def _fmt_money(val):
                try:
                    n = int(round(float(val)))
                except Exception:
                    return ""
                return f"{n:,}".replace(",", " ")

            c.delete("all")
            c.img_refs = []

            if df is None or len(df) == 0:
                c.create_text(10, 10, text="Brak danych klasyfikacji MSC.", anchor="nw")
                return

            # dopilnuj wymaganych kolumn
            for col in ["Lp.", "Drużyna", "Kraj", "Punkty", "Finanse (miejsce)", "Finanse (suma)", "Ranking FIS"]:
                if col not in df.columns:
                    df[col] = 0 if col != "Drużyna" and col != "Kraj" else ""

            # kolumny pokazywane (bez 'Suma')
            cols = ["Lp.", "Drużyna", "Kraj", "Punkty", "Finanse (miejsce)", "Finanse (suma)", "Ranking FIS"]

            width = max(int(c.winfo_width()), 900)
            margin_x = 10
            margin_y = 10
            row_h = 24

            # szerokości: Drużyna dostaje najwięcej
            col_widths = {
                "Lp.": 40,
                "Drużyna": 260,
                "Kraj": 60,
                "Punkty": 80,
                "Finanse (miejsce)": 130,
                "Finanse (suma)": 130,
                "Ranking FIS": 80,
            }

            total_w = sum(col_widths.values())
            scale = (width - 2 * margin_x) / total_w if total_w > 0 else 1.0
            for k in col_widths:
                col_widths[k] = int(col_widths[k] * scale)

            # pozycje X
            x = margin_x
            col_centers = {}
            for col in cols:
                w = col_widths[col]
                col_centers[col] = x + w / 2
                x += w

            # nagłówki
            y = margin_y
            c.create_rectangle(margin_x, y, width - margin_x, y + row_h, fill="#f0f0f0", outline="")
            for col in cols:
                c.create_text(col_centers[col], y + row_h / 2, text=col, anchor="center", font=("TkDefaultFont", 9, "bold"))

            y += row_h

            from flags_cache import FLAG_CACHE as _FLAG_CACHE

            # wiersze
            for _, r in df.iterrows():
                lp = r.get("Lp.", "")
                team = str(r.get("Drużyna", "") or "")
                nat = str(r.get("Kraj", "") or "").upper()
                pts = r.get("Punkty", "")
                fin_place = _fmt_money(r.get("Finanse (miejsce)", ""))
                fin_sum = _fmt_money(r.get("Finanse (suma)", ""))
                rank = r.get("Ranking FIS", "")

                c.create_rectangle(margin_x, y, width - margin_x, y + row_h, fill="#ffffff", outline="")

                # Lp.
                c.create_text(col_centers["Lp."], y + row_h / 2, text=lp, anchor="center")

                # Drużyna + flaga
                img = _flag_cached(nat)
                dru_left = col_centers["Drużyna"] - col_widths["Drużyna"] / 2 + 4
                if img:
                    c.img_refs.append(img)
                    c.create_image(dru_left, y + row_h / 2, image=img, anchor="w")
                    c.create_text(dru_left + 22, y + row_h / 2, text=team, anchor="w")
                else:
                    c.create_text(dru_left, y + row_h / 2, text=team, anchor="w")

                # reszta wycentrowana
                c.create_text(col_centers["Kraj"], y + row_h / 2, text=nat, anchor="center")
                c.create_text(col_centers["Punkty"], y + row_h / 2, text=str(pts), anchor="center")
                c.create_text(col_centers["Finanse (miejsce)"], y + row_h / 2, text=fin_place, anchor="center")
                c.create_text(col_centers["Finanse (suma)"], y + row_h / 2, text=fin_sum, anchor="center")
                c.create_text(col_centers["Ranking FIS"], y + row_h / 2, text=str(rank), anchor="center")

                y += row_h

            c.configure(scrollregion=(0, 0, width, y + margin_y))


    ttk.Button(frame_q_top, text="Odśwież", command=_cc_q_reload)\
        .pack(side="left", padx=(6, 0))

    ttk.Button(
        frame_q_top,
        text="Losuj grupy",
        command=lambda: _cc_draw_groups_for_dir(cc_dir_var.get())
    ).pack(side="left", padx=(6, 0))

    # pierwsze wczytanie przy starcie
    try:
        _cc_q_reload()
    except Exception:
        pass

    def _build_cc_groups_tab(parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 4))

        ttk.Button(
            top,
            text="Poukładaj fazę pucharową",
            command=lambda: _cc_build_cup_from_groups(cc_dir_var.get()),
        ).pack(side="left")

        ttk.Button(
            top,
            text="Odśwież z plików",
            command=_cc_groups_reload,
        ).pack(side="right")

        grid = ttk.Frame(frame)
        grid.pack(fill="both", expand=True)

        # 4x1: każda grupa w osobnym wierszu
        for r in range(4):
            grid.rowconfigure(r, weight=1)
        grid.columnconfigure(0, weight=1)

        for row, g in enumerate(("A", "B", "C", "D")):
            box = ttk.Labelframe(grid, text=f"Grupa {g}")
            box.grid(row=row, column=0, sticky="nsew", padx=4, pady=4)

            widget, ft = create_frozen_table(
                parent=box,
                left_key="Lp.",
                left_title="Lp.",
                left_width=60,
                tree_text_key="Drużyna",
                tree_title="Drużyna",
                right_cols=[
                    ("Kraj", 70, "center"),
                    ("Punkty Zdobyte", 120, "center"),
                    ("Punkty Stracone", 120, "center"),
                    ("Minipunkty", 120, "center"),
                ],
                image_from_row=lambda r, _g=g: _flag_cached(str(r.get("Kraj", "")).strip()),
                height=6,
            )
            widget.pack(fill="both", expand=True)

            # zapisz FrozenTable dla grupy (A/B/C/D)
            cc_groups[g] = ft

        return frame

    def _build_cc_schedule_tab(parent):
        from tkinter import ttk
        nonlocal tv_cc_schedule

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 4))

        ttk.Button(
            top,
            text="Generuj terminarz z grup",
            command=_cc_schedule_reload,
        ).pack(side="left")

        frame_tbl = ttk.Frame(frame)
        frame_tbl.pack(fill="both", expand=True)

        cols = ("Kolejka", "Grupa", "Mecz", "Drużyna1", "Kraj1", "Drużyna2", "Kraj2")
        tv = ttk.Treeview(frame_tbl, columns=cols, show="headings", height=20)

        for name, width, align in [
            ("Kolejka", 70, "center"),
            ("Grupa",   60, "center"),
            ("Mecz",    70, "center"),
            ("Drużyna1", 180, "w"),
            ("Kraj1",    70, "center"),
            ("Drużyna2", 180, "w"),
            ("Kraj2",    70, "center"),
        ]:
            tv.heading(name, text=name)
            tv.column(name, width=width, anchor=align, stretch=(align != "center"))

        tv.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(frame_tbl, orient="vertical", command=tv.yview)
        vsb.pack(side="right", fill="y")
        tv.configure(yscrollcommand=vsb.set)

        tv_cc_schedule = tv
        return frame

    def _build_cc_cup_tab(parent):
        from tkinter import ttk
        nonlocal cc_cup_canvas

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        # górny pasek przycisków (to możesz mieć już zrobione – zachowaj swoje)
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 4))

        ttk.Button(
            top,
            text="Poukładaj fazę pucharową",
            command=lambda: _cc_build_cup_from_groups(cc_dir_var.get()),
        ).pack(side="left")

        ttk.Button(
            top,
            text="Uaktualnij drabinkę z wyników",
            command=lambda: _cc_cup_apply_results(cc_dir_var.get()),
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            top,
            text="Odśwież z pliku",
            command=_cc_cup_reload,   # ważne, żeby istniało _cc_cup_reload
        ).pack(side="right")

        # tu już sama część z Canvasem
        frame_canvas = ttk.Frame(frame)
        frame_canvas.pack(fill="both", expand=True)

        import tkinter as tk
        canvas = tk.Canvas(frame_canvas, background="white")
        vscroll = ttk.Scrollbar(frame_canvas, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        frame_canvas.rowconfigure(0, weight=1)
        frame_canvas.columnconfigure(0, weight=1)

        def _on_cc_cup_mousewheel(event):
            # Windows / macOS
            if hasattr(event, "delta") and event.delta != 0:
                step = -1 if event.delta > 0 else 1
            else:
                # Linux (Button-4 / Button-5)
                if event.num == 4:
                    step = -1
                elif event.num == 5:
                    step = 1
                else:
                    step = 0
            if step:
                canvas.yview_scroll(step, "units")
            return "break"

        canvas.bind("<MouseWheel>", _on_cc_cup_mousewheel)
        canvas.bind("<Button-4>", _on_cc_cup_mousewheel)
        canvas.bind("<Button-5>", _on_cc_cup_mousewheel)

        cc_cup_canvas = canvas   # zapamiętujemy referencję

        return frame

    def _build_cc_final_tab(parent):
        import tkinter as tk
        from tkinter import ttk

        nonlocal cc_final_canvas

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 4))

        # lokalny handler, żeby widzieć błędy i mieć pewność, że kliknięcie coś robi
        def _on_cc_final_click():
            print("[DEBUG] CC final: kliknięto przycisk przelicz")
            try:
                _cc_final_reload()
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("CC – klasyfikacja końcowa", str(e))

        ttk.Button(
            top,
            text="Przelicz klasyfikację końcową CC",
            command=_on_cc_final_click,
        ).pack(side="left")


        ttk.Label(top, textvariable=cc_dir_var).pack(side="left", padx=8)

        frame_tbl = ttk.Frame(frame)
        frame_tbl.pack(fill="both", expand=True)

        canvas = tk.Canvas(frame_tbl, highlightthickness=0, bg="white")
        vsb = ttk.Scrollbar(frame_tbl, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(frame_tbl, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        frame_tbl.rowconfigure(0, weight=1)
        frame_tbl.columnconfigure(0, weight=1)

        cc_final_canvas = canvas
        canvas.img_refs = []

        def _on_wheel(event):
            delta = getattr(event, "delta", 0)
            if delta:
                step = -1 if delta > 0 else 1
            else:
                num = getattr(event, "num", None)
                if num == 4:
                    step = -1
                elif num == 5:
                    step = 1
                else:
                    step = 0
            if step:
                canvas.yview_scroll(step, "units")
                return "break"

        canvas.bind("<MouseWheel>", _on_wheel)
        canvas.bind("<Button-4>", _on_wheel)
        canvas.bind("<Button-5>", _on_wheel)

        # jednorazowe przeliczenie przy budowie zakładki (tylko jeśli funkcja już istnieje)
        func = globals().get("_cc_final_reload")
        if func is not None:
            try:
                func()
            except Exception as e:
                print("[DEBUG] CC final: błąd przy automatycznym przeliczeniu:", e)

        return frame

    def _build_msc_tab(self, parent, sex: str):
        """
        Zakładka MSC dla MEN / WOMEN.

        Layout:
        - górny pasek: folder + przyciski
        - Notebook z podzakładkami:
            Q / Grupy / Terminarz / Puchar
        """
        sex = str(sex or "").upper()[:1]
        if sex not in ("M", "W"):
            raise ValueError("sex musi być 'M' albo 'W'")

        # --------- GÓRNY PASEK (folder + przyciski) ---------
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=8, pady=(8, 4))

        dir_var = self.msc_m_dir_var if sex == "M" else self.msc_w_dir_var

        ttk.Label(top, text="Folder MSC:").pack(side="left")
        ent = ttk.Entry(top, textvariable=dir_var, width=40)
        ent.pack(side="left", padx=(4, 6))

        def _browse():
            path = filedialog.askdirectory(title="Wybierz folder z wynikami MSC")
            if path:
                dir_var.set(path)

        ttk.Button(top, text="…", width=3, command=_browse).pack(side="left", padx=(0, 8))

        # --------- NOTEBOOK: Q / Grupy / Terminarz / Puchar / Klasyfikacja ---------
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        tab_q = ttk.Frame(nb)
        tab_groups = ttk.Frame(nb)
        tab_sched = ttk.Frame(nb)
        tab_cup = ttk.Frame(nb)
        tab_classif = ttk.Frame(nb)

        nb.add(tab_q, text="Q")
        nb.add(tab_groups, text="Grupy")
        nb.add(tab_sched, text="Terminarz")
        nb.add(tab_cup, text="Puchar")
        nb.add(tab_classif, text="Klasyfikacja")


        # --- Q: tabelka kwalifikacji ---
        q_frame = _build_msc_q_table(tab_q, sex=sex)
        q_frame.pack(fill="both", expand=True)

        def _reload_q():
            try:
                df = _msc_q_summary_from_dir(dir_var.get().strip() or ".", sex=sex)
            except Exception as e:
                print(f"[MSC-Q] Brak pliku kwalifikacji ({sex}): {e}")
                return
            q_frame.populate_from_df(df)

        ttk.Button(top, text="Przelicz Q (MSC)", command=_reload_q).pack(side="left", padx=(8, 0))

        # przycisk losowania grup dla danej płci
        ttk.Button(
            top,
            text="Losuj grupy (MSC)",
            command=lambda: (_msc_draw_groups_for_dir(dir_var.get(), sex), _msc_groups_reload(sex)),
        ).pack(side="left", padx=(6, 0))
        # --- zakładka GRUPY + TERMINARZ + PUCHAR dla tej płci ---
        _build_msc_groups_tab(tab_groups, sex=sex)
        _build_msc_schedule_tab(tab_sched, sex=sex)
        _build_msc_cup_tab(tab_cup, sex=sex)
        _build_msc_classif_tab(tab_classif, sex=sex)


        # automatycznie: przelicz Q i spróbuj wczytać istniejące grupy / terminarz
        _reload_q()
        try:
            _msc_groups_reload(sex)
        except Exception:
            pass
        try:
            _msc_classif_recompute_and_redraw(sex)
        except Exception:
            pass
        try:
            _msc_classif_reload(sex)
        except Exception:
            pass


    # zbuduj zakładkę „Grupy” + od razu wczytaj pliki, jeśli są
    _build_cc_groups_tab(tab_cc_groups)
    try:
        _cc_groups_reload()
    except Exception:
        pass

    # zakładka „Terminarz” – mecze w grupach
    _build_cc_schedule_tab(tab_cc_schedule)

    # po zbudowaniu tabeli terminarza od razu go uzupełnij
    try:
        _cc_schedule_reload()
    except Exception:
        pass

    # zakładka „Puchar” – podgląd drabinki
    _build_cc_cup_tab(tab_cc_cup)

    # i od razu wczytaj drabinkę z pliku, jeśli istnieje
    try:
        _cc_cup_reload()
    except Exception:
        pass

    # zakładka „Klasyfikacja końcowa” – puchar + Q
    _build_cc_final_tab(tab_cc_final)

    # Źródło rosteru: GUI DB vs Excel
    roster_source = tk.StringVar(master=root, value="GUI")
    src_bar = ttk.Frame(tab_params); src_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,0))
    ttk.Label(src_bar, text="Źródło rosteru:").pack(side="left")
    ttk.Radiobutton(src_bar, text="Baza w GUI", variable=roster_source, value="GUI").pack(side="left", padx=(6,12))
    ttk.Radiobutton(src_bar, text="Excel (legacy)", variable=roster_source, value="XLSX").pack(side="left")

    settings_frame = ttk.Frame(tab_params)
    settings_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    settings_frame.columnconfigure(0, weight=1)
    settings_frame.columnconfigure(1, weight=1)

    left = ttk.Frame(settings_frame, padding=8)
    right = ttk.Frame(settings_frame, padding=8)
    left.grid(row=0, column=0, sticky="nsew")
    right.grid(row=0, column=1, sticky="nsew")

    self = tl  # ułatwienie: wiążemy z toplevelem

    # model pod combobox (w tym DF z csv, żeby po wyborze odczytać K/HS)
    self._hills_df_team = None
    self.var_hill_team = hill_name  # używamy istniejącej zmiennej z Twojego GUI

    row = left  # lewa kolumna parametrów
    ttk.Label(row, text="Skocznia:").grid(row=row.grid_size()[1], column=0, sticky="e", padx=4, pady=2)
    cbo = ttk.Combobox(row, textvariable=self.var_hill_team, state="readonly", width=36)
    cbo.grid(row=row.grid_size()[1]-1, column=1, sticky="w", padx=4, pady=2)
    self.cbo_hill_team = cbo
    enable_combobox_wheel(self.cbo_hill_team)
    self.cbo_hill_team.focus_set()
    self.cbo_hill_team.bind("<FocusIn>", lambda e: self.cbo_hill_team.focus_set(), add="+")


    def _load_hills_csv_team():
        resolved = _find_nearby_file("Skocznie S45.csv", alt_patterns=["*Skocznie* S45*.csv"])
        if not resolved:
            return
        path = Path(resolved)

        # wczytaj CSV z polskim cp1250 na wypadek ogonków
        last = None
        for enc in ("utf-8-sig", "utf-8", "cp1250"):
            try:
                df = pd.read_csv(path, sep=None, engine="python", encoding=enc)
                break
            except Exception as e:
                last = e
                df = None
        if df is None:
            try:
                df = pd.read_csv(path, sep=";", encoding="cp1250")
            except Exception:
                messagebox.showwarning("Skocznie", f"Nie mogę wczytać CSV: {path}\n{last}")
                return

        # upewnij się, że mamy kolumny używane do etykiet i parametrów
        for c in ("Miasto", "Skocznia", "K", "HS", "Kraj"):
            if c not in df.columns:
                df[c] = ""

        df["K_num"]  = pd.to_numeric(df["K"],  errors="coerce")
        df["HS_num"] = pd.to_numeric(df["HS"], errors="coerce")
        df = df.dropna(subset=["K_num", "HS_num"]).copy()

        def _label(r):
            miasto = str(r.get("Miasto","")).strip()
            k      = int(r.get("K_num", 0))
            hs     = int(r.get("HS_num", 0))
            nat    = str(r.get("Kraj","")).strip().upper()
            core   = f"{miasto} (K{k}/HS{hs})".strip()
            return f"[{nat}] {core}" if nat else core

        df["__label"] = df.apply(_label, axis=1)
        try:
            df = df.sort_values(["Kraj","Miasto","HS_num"], ascending=[True, True, False], kind="mergesort")
        except Exception:
            df = df.sort_values("__label")

        self._hills_df_team = df.reset_index(drop=True)
        self.cbo_hill_team["values"] = self._hills_df_team["__label"].tolist()
        try:
            # zsynchronizuj cache z faktycznym stanem
            self.cbo_hill_team._mw_idx = _current_index_of(self.cbo_hill_team)
        except Exception:
            pass
        # jeśli w polu było coś wpisane, spróbuj dopasować
        curr = (self.var_hill_team.get() or "").strip().lower()
        if curr:
            vals = self.cbo_hill_team["values"]
            try:
                idx = next((i for i, s in enumerate(vals) if curr in str(s).lower()), -1)
                if idx >= 0:
                    self.cbo_hill_team.current(idx)
            except Exception:
                pass

    def _on_hill_selected_team(*_):
        """Po wyborze skoczni ustaw K/HS; 'Punkty za metr' wyczyść (auto)."""
        try:
            idx = self.cbo_hill_team.current()
            if idx < 0 or self._hills_df_team is None:
                return
            r = self._hills_df_team.iloc[idx]
            miasto = str(r.get("Miasto","")).strip()
            hs     = int(r.get("HS_num", 0))
            k      = int(r.get("K_num", 0))

            pretty = f"{miasto} (K{k}/HS{hs})".strip()
            self.var_hill_team.set(pretty)

            k_value.set(str(k))
            hs_value.set(str(hs))
            meter_value.set("")  # zostaw puste → silnik wyliczy z K
        except Exception as e:
            messagebox.showerror("Skocznie", f"Nie udało się ustawić parametrów: {e}")

    self.cbo_hill_team.bind("<<ComboboxSelected>>", _on_hill_selected_team)
    
    def add_row(frame, label, var, widget=None, width=12, expand=False):
        r = frame.grid_size()[1]
        ttk.Label(frame, text=label).grid(row=r, column=0, sticky="e", padx=4, pady=2)
        ent = None
        if isinstance(var, (tk.StringVar, tk.DoubleVar, tk.IntVar)):
            ent = ttk.Entry(frame, textvariable=var, width=width)
            ent.grid(row=r, column=1, sticky=("ew" if expand else "w"), padx=4, pady=2)
            if expand:
                frame.columnconfigure(1, weight=1)
        if widget is not None:
            widget.grid(row=r, column=2, sticky="w", padx=4, pady=2)
        return ent

    # LEFT content
    ttk.Label(left, text="Podstawowe", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,4))
    add_row(left, "Nazwa skoczni:", hill_name, width=30)
    add_row(left, "Punkt K:", k_value, width=8)
    add_row(left, "HS:", hs_value, width=8)
    add_row(left, "Punkty za metr (opcjonalnie):", meter_value, width=8)
    add_row(left, "Średni wiatr (m/s):", wind_mean_value, width=8)
    add_row(left, "Odchylenie wiatru (m/s):", wind_sd_value, width=8)
    add_row(left, "Belka bazowa:", gate_value, width=8)
    add_row(left, "Losowość:", randomness_value, width=8)
    add_row(left, "Regresja elit:", elite_regress_value, width=8)

    ttk.Separator(left, orient="horizontal").grid(row=left.grid_size()[1], column=0, columnspan=3, sticky="ew", pady=(6,6))
    ttk.Label(left, text="Belka / Wiatr / Sędziowie", font=("TkDefaultFont", 10, "bold")).grid(row=left.grid_size()[1], column=0, columnspan=3, sticky="w")
    add_row(left, "Punkty za 1 stopień belki:", gate_pts_step, width=8)
    add_row(left, "Szansa zmiany belki:", p_gate_change, width=8)
    add_row(left, "Maks. skok zmiany belki:", max_gate_delta, width=6)
    add_row(left, "Autokorelacja wiatru:", wind_phi, width=8)
    add_row(left, "Wpływ wiatru na wybicie:", wind_takeoff_gain, width=8)
    add_row(left, "Wpływ wiatru w locie:", wind_flight_gain, width=8)
    add_row(left, "Spójność not sędziów:", judges_rho, width=8)

    # RIGHT content
    ttk.Label(right, text="Format zawodów", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    add_row(right, "Liczba finalistów:", finalists_n, width=6)
    add_row(right, "Liczba serii (1/2):", num_series, width=6)

    def choose_outdir():
        d = filedialog.askdirectory()
        if d:
            outdir.set(d)
    btn_outdir = ttk.Button(right, text="Wybierz...", command=choose_outdir)
    add_row(right, "Katalog wyjściowy:", outdir, btn_outdir, width=26, expand=True)
    add_row(right, "Wzór nazwy pliku:", name_pattern, width=26, expand=True)
    ttk.Checkbutton(right, text="Tylko zapis do Excela (bez podglądu)", variable=only_save).grid(row=right.grid_size()[1], column=0, columnspan=3, sticky="w", pady=2)
    ttk.Checkbutton(right, text="Otwórz plik w Excelu po zapisie", variable=auto_open).grid(row=right.grid_size()[1], column=0, columnspan=3, sticky="w", pady=2)
    show_fis_team = tk.BooleanVar(value=False)
    ttk.Checkbutton(right,text="Pokaż Punkty FIS",variable=show_fis_team).grid(row=right.grid_size()[1], column=0, columnspan=3, sticky="w", pady=2)


    # przycisk Start
    def run_and_save_config():
        state = {
            "excel": excel_path.get(),
            "sheet_name": sheet_name.get(),
            "hill_name": hill_name.get(),
            "k": k_value.get(), "hs": hs_value.get(), "meter": meter_value.get(),
            "wind_mean": wind_mean_value.get(), "wind_sd": wind_sd_value.get(),
            "gate": gate_value.get(), "randomness": randomness_value.get(),
            "elite_regress": elite_regress_value.get(),
            "gate_points_per_step": gate_pts_step.get(), "p_gate_change": p_gate_change.get(),
            "max_gate_delta": max_gate_delta.get(), "wind_phi": wind_phi.get(),
            "wind_takeoff_gain": wind_takeoff_gain.get(), "wind_flight_gain": wind_flight_gain.get(),
            "judges_rho": judges_rho.get(),
            "finalists_n": finalists_n.get(), "num_series": num_series.get(),
            "outdir": outdir.get(), "name_pattern": name_pattern.get(),
            "only_save": only_save.get(), "auto_open": auto_open.get(), "show_fis_team_points": show_fis_team.get(),
        }
        save_config(state)
        run_simulation()

    ttk.Button(tab_params, text="Start symulacji", command=run_and_save_config).grid(row=1, column=0, pady=(0,8))

    # --- zakładki MSC (MEN / WOMEN) na głównym notebooku ---
    tab_msc_m = ttk.Frame(notebook_main)
    tab_msc_w = ttk.Frame(notebook_main)

    _build_msc_tab(self, tab_msc_m, sex="M")
    _build_msc_tab(self, tab_msc_w, sex="W")

    notebook_main.add(tab_msc_m, text="MSC-MEN")
    notebook_main.add(tab_msc_w, text="MSC-WOMEN")

    # ---------- TAB: WYNIKI ----------
    tab_results = ttk.Frame(notebook_main)
    notebook_main.add(tab_results, text="Wyniki")
    tab_results.rowconfigure(0, weight=1)
    tab_results.columnconfigure(0, weight=1)

    notebook_res = ttk.Notebook(tab_results)
    notebook_res.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    # --- KLASYFIKACJA: zamrożone "Miejsce" + flaga przy "Drużyna" ---
    frame_class_outer, table_class = create_frozen_table(
        parent=notebook_res,
        left_key="Miejsce",
        left_title="Miejsce",
        left_width=70,
        tree_text_key="Drużyna",
        tree_title="Drużyna",
        right_cols=[
            ("Kraj", 80, "w"),
            ("Jumper1", 110, "w"),
            ("Jumper2", 110, "w"),
            ("Jumper3", 110, "w"),
            ("Jumper4", 110, "w"),
            ("Suma", 130, "e"), 
            ("Punkty FIS (TEAM)", 130, "e"),
        ],
        image_from_row=lambda r: _flag_cached(str(r.get("Kraj","")).strip()),
        height=26,
    )
    notebook_res.add(frame_class_outer, text="Klasyfikacja 2-wierszowa")
    _center_cols_except_team(table_class.tvR, team_col="Drużyna")

    # --- U P A D K I: jak w IND GUI ---
    # Zawodnik (z flagą) + Kraj, Seria, Płeć, Lekarz, Infrastr., Odległość, Kontuzje, ΔUM/ΔForma
    frame_falls_outer, tv_falls = add_player_table_with_flags(
        notebook_res,
        columns=(
            "Kraj",
            "Seria",
            "Płeć",
            "Lekarz",
            "Infrastr.",
            "Odległość",
            "Kontuzja (rodzaj)",
            "Kontuzja (dni)",
            "Długość kontuzji (WEEK)",
            "Sex",
            "ΔUM (kontuzja)",
            "ΔForma (kontuzja)",
        ),
        text_heading="Zawodnik",
        height=22
    )
    notebook_res.add(frame_falls_outer, text="Upadki")

    # --- S E R I A 1: Zawodnik (z flagą), Kraj, Odległość, Punkty ---
    frame_r1_outer, tv_r1 = add_player_table_with_flags(
        notebook_res,
        columns=("Kraj", "Odległość", "Punkty"),
        text_heading="Zawodnik",
        height=22
    )
    notebook_res.add(frame_r1_outer, text="Seria 1")

    # --- S E R I A 2: Zawodnik (z flagą), Kraj, Odległość, Punkty ---
    frame_r2_outer, tv_r2 = add_player_table_with_flags(
        notebook_res,
        columns=("Kraj", "Odległość", "Punkty"),
        text_heading="Zawodnik",
        height=22
    )
    notebook_res.add(frame_r2_outer, text="Seria 2")

    # --- Pasek: sezon/cykl + aktualizacja klasyfikacji NATIONS (TEAM) ---
    frame_update_cls = ttk.Frame(tab_results)
    frame_update_cls.grid(row=1, column=0, sticky="ew", padx=8, pady=(0,8))
    frame_update_cls.columnconfigure(10, weight=1)

    ttk.Label(frame_update_cls, text="Sezon:").grid(row=0, column=0, sticky="w")
    _team_cls_season_var = tk.StringVar(value="S45")
    ttk.Entry(frame_update_cls, textvariable=_team_cls_season_var, width=6).grid(row=0, column=1, padx=(4,12))

    ttk.Label(frame_update_cls, text="Cykl (np. WC-M):").grid(row=0, column=2, sticky="w")
    _team_cls_cycle_var = tk.StringVar(value="WC-M")
    ttk.Entry(frame_update_cls, textvariable=_team_cls_cycle_var, width=10).grid(row=0, column=3, padx=(4,12))

    # --- NOWE: checkbox MIX ---
    _team_cls_mix_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        frame_update_cls,
        text="MIX (50% pkt)",
        variable=_team_cls_mix_var
    ).grid(row=0, column=4, padx=(0,12), sticky="w")

    ttk.Button(
        frame_update_cls, text="Aktualizuj klasyfikacje",
        command=lambda: _team_update_nations_from_results(
            _team_cls_season_var.get().strip(),
            _team_cls_cycle_var.get().strip(),
            bool(_team_cls_mix_var.get())
        )
    ).grid(row=0, column=5, padx=(4,0))

    ttk.Button(
        frame_update_cls,
        text="Aktualizuj bazę z Upadków…",
        command=self._open_injury_update_dialog
    ).grid(row=0, column=6, padx=(12, 0))


    # --- Pasek: mistrzostwa – zapis TEAM do CSV ---
    frame_champs = ttk.Frame(tab_results)
    frame_champs.grid(row=2, column=0, sticky="ew", padx=8, pady=(0,8))
    frame_champs.columnconfigure(10, weight=1)

    ttk.Label(frame_champs, text="Mistrzostwa – sezon:").grid(row=0, column=0, sticky="w")
    _team_ch_season_var = tk.StringVar(value="S45")
    ttk.Entry(frame_champs, textvariable=_team_ch_season_var, width=6)\
        .grid(row=0, column=1, padx=(4,12))

    ttk.Label(
        frame_champs,
        text="Kod pliku (np. WCH_M_TEAM / SFWC_X_TEAM):"
    ).grid(row=0, column=2, sticky="w")
    _team_ch_code_var = tk.StringVar(value="")
    ttk.Entry(frame_champs, textvariable=_team_ch_code_var, width=22)\
        .grid(row=0, column=3, padx=(4,12))

    ttk.Button(
        frame_champs,
        text="Zapisz TEAM → CSV (mistrzostwa)",
        command=lambda: _export_team_champs_results(
            _team_ch_season_var.get().strip(),
            _team_ch_code_var.get().strip()
        )
    ).grid(row=0, column=4, padx=(4,0))

    # --- Pasek: CC – aktualizacja grup / pucharu ---
    frame_cc_groups_update = ttk.Frame(tab_results)
    frame_cc_groups_update.grid(row=3, column=0, sticky="ew", padx=8, pady=(0,8))
    frame_cc_groups_update.columnconfigure(10, weight=1)

    ttk.Label(frame_cc_groups_update, text="CC – aktualizacja:").grid(row=0, column=0, sticky="w")

    _cc_round_var = tk.StringVar(value="1")

    cb_cc_round = ttk.Combobox(
        frame_cc_groups_update,
        textvariable=_cc_round_var,
        values=("1", "2", "3", "1/4", "1/2", "Finał"),
        width=8,
        state="readonly"
    )
    cb_cc_round.grid(row=0, column=1, sticky="w", padx=(4, 8))

    def _cc_update_any_from_results():
        from tkinter import messagebox

        val = _cc_round_var.get().strip()
        if val in ("1", "2", "3"):
            _cc_update_groups_from_results(val)
        elif val in ("1/4", "1/2", "Finał"):
            _cc_update_bracket_from_results(val)
        else:
            messagebox.showwarning(
                "CC – aktualizacja",
                "Wybierz kolejkę (1–3) albo fazę pucharu (1/4, 1/2, Finał)."
            )

    ttk.Button(
        frame_cc_groups_update,
        text="Aktualizuj CC",
        command=_cc_update_any_from_results
    ).grid(row=0, column=2, padx=(12,0), sticky="w")

    # --- MSC: aktualizacja z wyników (MEN / WOMEN) ---
    frame_msc_update = ttk.Frame(tab_results)
    # dopasuj wiersz tak, żeby nie nachodziło na inne – jeśli CC jest w row=3,
    # to tutaj row=4 jest OK
    frame_msc_update.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
    frame_msc_update.columnconfigure(5, weight=1)

    # ---- MSC-MEN ----
    ttk.Label(frame_msc_update, text="MSC-MEN:").grid(row=0, column=0, sticky="w")

    _msc_m_round_var = tk.StringVar(value="1")
    cmb_msc_m = ttk.Combobox(
        frame_msc_update,
        textvariable=_msc_m_round_var,
        values=("1", "2", "3", "1/4", "1/2", "Finał"),
        width=8,
        state="readonly",
    )
    cmb_msc_m.grid(row=0, column=1, sticky="w", padx=(4, 8))
    try:
        enable_combobox_wheel(cmb_msc_m)  # jeśli helper jest w pliku, zadziała
    except Exception:
        pass

    ttk.Button(
        frame_msc_update,
        text="Aktualizuj MSC-MEN",
        command=lambda: _msc_update_any_from_results("M", _msc_m_round_var.get()),
    ).grid(row=0, column=2, sticky="w", padx=(4, 0))

    # ---- MSC-WOMEN ----
    ttk.Label(frame_msc_update, text="MSC-WOMEN:").grid(row=1, column=0, sticky="w", pady=(4, 0))

    _msc_w_round_var = tk.StringVar(value="1")
    cmb_msc_w = ttk.Combobox(
        frame_msc_update,
        textvariable=_msc_w_round_var,
        values=("1", "2", "3", "1/4", "1/2", "Finał"),
        width=8,
        state="readonly",
    )
    cmb_msc_w.grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(4, 0))
    try:
        enable_combobox_wheel(cmb_msc_w)
    except Exception:
        pass

    ttk.Button(
        frame_msc_update,
        text="Aktualizuj MSC-WOMEN",
        command=lambda: _msc_update_any_from_results("W", _msc_w_round_var.get()),
    ).grid(row=1, column=2, sticky="w", padx=(4, 0), pady=(4, 0))

    # === SWISS – logika turnieju drużynowego ===
    def _swiss_read_matches_from_dir(dir_path):
        """
        Czyta wszystkie mecze SWISS z pliku:
            S45_SWISS.csv
        w katalogu dir_path (np. ./S45/Team S45).

        Zwraca DataFrame z kolumnami:
        Runda;Mecz;Drużyna1;Kraj1;PktM1;Minipunkty1;MinipunktyM1;MinipunktyW1;MinipunktyX1;
        Drużyna2;Kraj2;PktM2;Minipunkty2;MinipunktyM2;MinipunktyW2;MinipunktyX2
        """
        import pandas as _pd
        from pathlib import Path as _Path

        dir_str = str(dir_path).strip() or "."
        p = _Path(dir_str) / "S45_SWISS.csv"
        if not p.is_file():
            print(f"[SWISS] Brak pliku z rundami: {p}")
            return _pd.DataFrame(
                columns=[
                    "Runda","Mecz",
                    "Drużyna1","Kraj1","PktM1","Minipunkty1","MinipunktyM1","MinipunktyW1","MinipunktyX1",
                    "Drużyna2","Kraj2","PktM2","Minipunkty2","MinipunktyM2","MinipunktyW2","MinipunktyX2",
                ]
            )

        df = _read_tab_any(p)
        if df is None:
            raise RuntimeError(f"Nie udało się wczytać pliku: {p}")

        # nazwy kolumn na sztywno – delikatne czyszczenie nagłówków + wywalenie BOM
        def _clean_col_name(c):
            s = str(c)
            # usuń BOM-y typu \ufeff, które Excel lubi doklejać
            s = s.replace("\ufeff", "").replace("\uFEFF", "")
            return s.strip()

        df.columns = [_clean_col_name(c) for c in df.columns]

        expected = [
            "Runda","Mecz",
            "Drużyna1","Kraj1","PktM1","Minipunkty1","MinipunktyM1","MinipunktyW1","MinipunktyX1",
            "Drużyna2","Kraj2","PktM2","Minipunkty2","MinipunktyM2","MinipunktyW2","MinipunktyX2",
        ]
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise RuntimeError(f"[SWISS] Brak kolumn w S45_SWISS.csv: {', '.join(missing)}")

        # bezpieczne typy liczbowe + wyliczenie Minipunkty1/2 jeśli ktoś ich nie podał
        def _to_float(v):
            try:
                if v is None or v == "":
                    return 0.0
                return float(str(v).replace(",", "."))
            except Exception:
                return 0.0

        for side in ("1", "2"):
            for col in ("PktM", "Minipunkty", "MinipunktyM", "MinipunktyW", "MinipunktyX"):
                name = f"{col}{side}"
                df[name] = df[name].map(_to_float)

            # zabezpieczenie: jeżeli Minipunkty* nie są spójne, nadpisz sumą M+W+X
            sum_val = df[f"MinipunktyM{side}"] + df[f"MinipunktyW{side}"] + df[f"MinipunktyX{side}"]
            mask = df[f"Minipunkty{side}"].isna() | (df[f"Minipunkty{side}"] <= 0)
            df.loc[mask, f"Minipunkty{side}"] = sum_val.loc[mask]

        return df[expected].copy()

    def _swiss_compute_table(df_matches):
        """
        Buduje klasyfikację SWISS:
        Lp.;Drużyna;Kraj;M;W;R;P;PktM;Minipunkty;MinipunktyM;MinipunktyW;MinipunktyX;Buchholz
        """
        import pandas as _pd
        from collections import defaultdict

        if df_matches is None or df_matches.empty:
            return _pd.DataFrame(
                columns=[
                    "Lp.","Drużyna","Kraj",
                    "M","W","R","P",
                    "PktM",
                    "Minipunkty","MinipunktyM","MinipunktyW","MinipunktyX",
                    "Buchholz",
                ]
            )

        def _key(team, nat):
            team = str(team or "").strip()
            nat = str(nat or "").strip().upper()
            if not team or not nat:
                return None
            return (team, nat)

        stats = {}
        opp_map = defaultdict(set)

        for _, row in df_matches.iterrows():
            k1 = _key(row.get("Drużyna1"), row.get("Kraj1"))
            k2 = _key(row.get("Drużyna2"), row.get("Kraj2"))
            if not k1 or not k2:
                continue

            def _get(side, col):
                return float(row.get(f"{col}{side}") or 0.0)

            pm1 = _get("1", "PktM")
            pm2 = _get("2", "PktM")

            def _bucket(key):
                if key not in stats:
                    stats[key] = {
                        "M": 0,
                        "W": 0,
                        "R": 0,
                        "P": 0,
                        "PktM": 0.0,
                        "Minipunkty": 0.0,
                        "MinipunktyM": 0.0,
                        "MinipunktyW": 0.0,
                        "MinipunktyX": 0.0,
                    }
                return stats[key]

            b1 = _bucket(k1)
            b2 = _bucket(k2)

            # mecze
            b1["M"] += 1
            b2["M"] += 1

            # wynik W/R/P na podstawie PktM
            if pm1 > pm2:
                b1["W"] += 1
                b2["P"] += 1
            elif pm1 < pm2:
                b1["P"] += 1
                b2["W"] += 1
            else:
                b1["R"] += 1
                b2["R"] += 1

            b1["PktM"] += pm1
            b2["PktM"] += pm2

            for col in ("Minipunkty", "MinipunktyM", "MinipunktyW", "MinipunktyX"):
                v1 = _get("1", col)
                v2 = _get("2", col)
                b1[col] += v1
                b2[col] += v2

            # Buchholz – lista przeciwników, sumujemy PktM po wszystkim
            opp_map[k1].add(k2)
            opp_map[k2].add(k1)

        if not stats:
            return _pd.DataFrame(
                columns=[
                    "Lp.","Drużyna","Kraj",
                    "M","W","R","P",
                    "PktM",
                    "Minipunkty","MinipunktyM","MinipunktyW","MinipunktyX",
                    "Buchholz",
                ]
            )

        # najpierw tabela bez Buchholza
        rows = []
        for (team, nat), s in stats.items():
            rows.append({
                "Drużyna": team,
                "Kraj": nat,
                "M": int(s["M"]),
                "W": int(s["W"]),
                "R": int(s["R"]),
                "P": int(s["P"]),
                "PktM": float(s["PktM"]),
                "Minipunkty": float(s["Minipunkty"]),
                "MinipunktyM": float(s["MinipunktyM"]),
                "MinipunktyW": float(s["MinipunktyW"]),
                "MinipunktyX": float(s["MinipunktyX"]),
            })

        df = _pd.DataFrame(rows)

        # ucięcie minipunktów do 1 miejsca po przecinku w tabeli
        for col in ["Minipunkty", "MinipunktyM", "MinipunktyW", "MinipunktyX"]:
            if col in df.columns:
                df[col] = (
                    _pd.to_numeric(df[col], errors="coerce")
                    .fillna(0.0)
                    .round(1)
                )

        # mapa PktM dla Buchholza
        pktm_map = {
            (r["Drużyna"], str(r["Kraj"]).strip().upper()): float(r["PktM"])
            for _, r in df.iterrows()
        }

        buchholz_vals = []
        for _, r in df.iterrows():
            key = (r["Drużyna"], str(r["Kraj"]).strip().upper())
            opps = opp_map.get(key, set())
            s = 0.0
            for opp in opps:
                s += float(pktm_map.get(opp, 0.0))
            buchholz_vals.append(s)

        df["Buchholz"] = buchholz_vals

        # Buchholz też przycinamy do 1 miejsca po przecinku
        df["Buchholz"] = (
            _pd.to_numeric(df["Buchholz"], errors="coerce")
            .fillna(0.0)
            .round(1)
        )

        # sortowanie końcowe
        df = df.sort_values(
            ["PktM", "Minipunkty", "MinipunktyM", "MinipunktyW", "MinipunktyX", "Buchholz"],
            ascending=[False, False, False, False, False, False],
            kind="stable",
        ).reset_index(drop=True)

        df.insert(0, "Lp.", _pd.RangeIndex(1, len(df) + 1))

        return df

    def _swiss_generate_first_round_from_seed():
        """
        Czyta S45_SWISS_Seed.csv z katalogu SWISS (domyślnie ./S45/Team S45),
        układa 1. rundę (parowanie top half vs bottom half wg Lp.)
        i zapisuje S45_SWISS.csv z pustymi punktami.
        """
        from pathlib import Path as _Path
        from tkinter import messagebox
        import pandas as _pd
        nonlocal _swiss_classif_last_df

        dir_path = _Path(swiss_dir_var.get().strip() or ".")
        seed_path = dir_path / "S45_SWISS_Seed.csv"

        if not seed_path.is_file():
            messagebox.showerror("SWISS – seed", f"Brak pliku seedów:\n{seed_path}")
            return

        df_seed = _read_tab_any(seed_path)
        if df_seed is None or df_seed.empty:
            messagebox.showerror("SWISS – seed", f"Plik seedów jest pusty lub nieczytelny:\n{seed_path}")
            return

        # Normalizacja nagłówków
        cols_map = {str(c).strip().lower(): c for c in df_seed.columns}

        lp_col = cols_map.get("lp.") or cols_map.get("lp")
        team_col = (
            cols_map.get("drużyna")
            or cols_map.get("druzyna")
            or cols_map.get("team")
            or cols_map.get("reprezentacja")
            or cols_map.get("nation")
        )
        nat_col = (
            cols_map.get("kraj")
            or cols_map.get("nat")
            or cols_map.get("kod")
            or cols_map.get("code")
        )

        if not lp_col or not team_col or not nat_col:
            messagebox.showerror(
                "SWISS – seed",
                "Plik S45_SWISS_Seed.csv musi mieć kolumny typu:\n"
                "Lp.;Drużyna;Kraj (lub ich oczywiste warianty)."
            )
            return

        df = df_seed[[lp_col, team_col, nat_col]].copy()
        df[lp_col] = _pd.to_numeric(df[lp_col], errors="coerce")
        df = df.dropna(subset=[lp_col])
        if df.empty:
            messagebox.showerror("SWISS – seed", "Brak poprawnych wartości Lp. w pliku seedów.")
            return

        df = df.sort_values(lp_col, ascending=True, kind="stable").reset_index(drop=True)

        n = len(df)
        if n < 2 or n % 2 != 0:
            messagebox.showerror(
                "SWISS – seed",
                f"Liczba drużyn musi być parzysta (np. 164). Obecnie: {n}."
            )
            return

        half = n // 2
        top = df.iloc[:half].reset_index(drop=True)
        bottom = df.iloc[half:].reset_index(drop=True)

        rows = []
        for i in range(half):
            t = top.iloc[i]
            b = bottom.iloc[i]

            team1 = str(t[team_col]).strip()
            nat1 = str(t[nat_col]).strip().upper()
            team2 = str(b[team_col]).strip()
            nat2 = str(b[nat_col]).strip().upper()

            rows.append({
                "Runda": 1,
                "Mecz": f"M{i+1}",
                "Drużyna1": team1,
                "Kraj1": nat1,
                "PktM1": 0,
                "Minipunkty1": 0,
                "MinipunktyM1": 0,
                "MinipunktyW1": 0,
                "MinipunktyX1": 0,
                "Drużyna2": team2,
                "Kraj2": nat2,
                "PktM2": 0,
                "Minipunkty2": 0,
                "MinipunktyM2": 0,
                "MinipunktyW2": 0,
                "MinipunktyX2": 0,
            })

        df_out = _pd.DataFrame(rows, columns=[
            "Runda","Mecz",
            "Drużyna1","Kraj1","PktM1","Minipunkty1","MinipunktyM1","MinipunktyW1","MinipunktyX1",
            "Drużyna2","Kraj2","PktM2","Minipunkty2","MinipunktyM2","MinipunktyW2","MinipunktyX2",
        ])

        out_path = dir_path / "S45_SWISS.csv"
        try:
            df_out.to_csv(out_path, sep=";", index=False, encoding="cp1250")
        except Exception as e:
            messagebox.showerror("SWISS – seed", f"Nie udało się zapisać S45_SWISS.csv:\n{e}")
            return

        # od razu przeładuj widok rund
        try:
            _swiss_reload_matches()
        except Exception:
            pass

        # wyczyść tabelę SWISS (żeby nie wisiały stare dane)
        try:
            if tv_swiss_table is not None:
                tv_swiss_table.delete(*tv_swiss_table.get_children())
        except Exception:
            pass

        # wyczyść uproszczoną klasyfikację SWISS
        try:
            if swiss_classif_ft is not None:
                swiss_classif_ft.set_dataframe(_pd.DataFrame())
                try:
                    swiss_classif_ft.autosize()
                except Exception:
                    pass
            _swiss_classif_last_df = None
        except Exception:
            pass

        messagebox.showinfo(
            "SWISS – 1. runda",
            f"Utworzono 1. rundę SWISS ({half} meczów)\n"
            f"na podstawie pliku:\n{seed_path}\n\n"
            f"Zapisano do:\n{out_path}"
        )


    def _swiss_generate_next_round():
        """
        Generuje kolejną rundę SWISS na podstawie aktualnej klasyfikacji:
        - bierze wszystkie rozegrane mecze z S45_SWISS.csv,
        - liczy tabelę (_swiss_compute_table),
        - sortuje wg PktM, Buchholza, Minipunktów (plus seed Lp., jeśli jest),
        - paruje 1–2, 3–4, 5–6 itd. z unikaniem rewanżów, jeśli to możliwe,
        - dopisuje nową rundę (Runda = max(Runda)+1) do S45_SWISS.csv.
        """
        from pathlib import Path as _Path
        from tkinter import messagebox
        import pandas as _pd

        dir_path = _Path(swiss_dir_var.get().strip() or ".")
        try:
            df_matches = _swiss_read_matches_from_dir(dir_path)
        except Exception as e:
            messagebox.showerror("SWISS – rundy", str(e))
            return

        if df_matches is None or df_matches.empty:
            messagebox.showerror("SWISS – rundy", "Brak meczów w S45_SWISS.csv – najpierw utwórz 1. rundę.")
            return

        # ustal obecną rundę
        try:
            max_round = int(float(df_matches["Runda"].max() or 0))
        except Exception:
            max_round = 0

        if max_round <= 0:
            messagebox.showerror("SWISS – rundy", "Nie wykryto żadnej rundy. Najpierw utwórz 1. rundę z seedów.")
            return

        # ostrzeżenie, jeśli w ostatniej rundzie masz mecze bez wyniku (PktM1+PktM2 = 0)
        mask_last = df_matches["Runda"] == max_round
        df_last = df_matches.loc[mask_last].copy()
        if not df_last.empty:
            no_res = (df_last["PktM1"].fillna(0.0) + df_last["PktM2"].fillna(0.0) <= 0.0).sum()
            if no_res > 0:
                if not messagebox.askyesno(
                    "SWISS – generowanie rundy",
                    f"W rundzie {max_round} jest jeszcze {no_res} mecz(ów) bez punktów.\n"
                    f"Czy mimo to wygenerować kolejną rundę?"
                ):
                    return

        # klasyfikacja po wszystkich dotychczasowych meczach
        try:
            df_table = _swiss_compute_table(df_matches)
        except Exception as e:
            messagebox.showerror("SWISS – klasyfikacja", f"Problem z przeliczeniem tabeli:\n{e}")
            return

        if df_table is None or df_table.empty:
            messagebox.showerror("SWISS – klasyfikacja", "Nie udało się zbudować tabeli SWISS.")
            return

        # opcjonalny tie-break z seedów (Lp. z S45_SWISS_Seed.csv)
        seed_lp = {}
        seed_path = dir_path / "S45_SWISS_Seed.csv"
        if seed_path.is_file():
            try:
                df_seed = _read_tab_any(seed_path)
            except Exception:
                df_seed = None
            if df_seed is not None and not df_seed.empty:
                cols_map = {str(c).strip().lower(): c for c in df_seed.columns}
                lp_col = cols_map.get("lp.") or cols_map.get("lp")
                team_col = (
                    cols_map.get("drużyna")
                    or cols_map.get("druzyna")
                    or cols_map.get("team")
                    or cols_map.get("reprezentacja")
                    or cols_map.get("nation")
                )
                nat_col = (
                    cols_map.get("kraj")
                    or cols_map.get("nat")
                    or cols_map.get("kod")
                    or cols_map.get("code")
                )
                if lp_col and team_col and nat_col:
                    tmp = df_seed[[lp_col, team_col, nat_col]].copy()
                    tmp[lp_col] = _pd.to_numeric(tmp[lp_col], errors="coerce")
                    tmp = tmp.dropna(subset=[lp_col])
                    for _, r in tmp.iterrows():
                        key = (str(r[team_col]).strip(), str(r[nat_col]).strip().upper())
                        seed_lp[key] = int(r[lp_col])

        def _key(team, nat):
            return (str(team or "").strip(), str(nat or "").strip().upper())

        # lista rozegranych par (żeby unikać rewanżów)
        played = set()
        for _, row in df_matches.iterrows():
            k1 = _key(row.get("Drużyna1"), row.get("Kraj1"))
            k2 = _key(row.get("Drużyna2"), row.get("Kraj2"))
            if not k1[0] or not k2[0]:
                continue
            played.add(frozenset((k1, k2)))

        # posortowana lista drużyn z tabeli
        teams = df_table[["Drużyna", "Kraj", "PktM", "Buchholz", "Minipunkty"]].copy()

        def _seed_pos(row):
            return seed_lp.get(_key(row["Drużyna"], row["Kraj"]), 999999)

        if seed_lp:
            teams["SeedLp"] = teams.apply(_seed_pos, axis=1)
            sort_cols = ["PktM", "Buchholz", "Minipunkty", "SeedLp"]
            asc = [False, False, False, True]
        else:
            sort_cols = ["PktM", "Buchholz", "Minipunkty"]
            asc = [False, False, False]

        teams = teams.sort_values(sort_cols, ascending=asc, kind="stable").reset_index(drop=True)

        n = len(teams)
        if n < 2 or n % 2 != 0:
            messagebox.showerror(
                "SWISS – generowanie",
                f"Liczba drużyn musi być parzysta, obecnie: {n}."
            )
            return

        records = teams.to_dict(orient="records")

        pairs = []
        used = set()

        # parowanie 1–2, 3–4, 5–6 z próbą unikania rewanżów
        i = 0
        while i < len(records):
            a = records[i]
            ka = _key(a["Drużyna"], a["Kraj"])
            if ka in used:
                i += 1
                continue

            j_choice = None
            for j in range(i + 1, len(records)):
                b = records[j]
                kb = _key(b["Drużyna"], b["Kraj"])
                if kb in used:
                    continue
                pair_key = frozenset((ka, kb))
                if pair_key not in played:
                    j_choice = j
                    break

            if j_choice is None:
                # nie da się uniknąć rewanżu – bierz pierwszego wolnego
                for j in range(i + 1, len(records)):
                    b = records[j]
                    kb = _key(b["Drużyna"], b["Kraj"])
                    if kb not in used:
                        j_choice = j
                        break

            if j_choice is None:
                i += 1
                continue

            b = records[j_choice]
            kb = _key(b["Drużyna"], b["Kraj"])

            used.add(ka)
            used.add(kb)
            pairs.append((a, b))
            i += 1

        if not pairs:
            messagebox.showerror("SWISS – generowanie", "Nie udało się wygenerować nowych par.")
            return

        next_round = max_round + 1

        new_rows = []
        for idx, (a, b) in enumerate(pairs, start=1):
            team1 = str(a["Drużyna"]).strip()
            nat1 = str(a["Kraj"]).strip().upper()
            team2 = str(b["Drużyna"]).strip()
            nat2 = str(b["Kraj"]).strip().upper()

            new_rows.append({
                "Runda": next_round,
                "Mecz": f"M{idx}",
                "Drużyna1": team1,
                "Kraj1": nat1,
                "PktM1": 0,
                "Minipunkty1": 0,
                "MinipunktyM1": 0,
                "MinipunktyW1": 0,
                "MinipunktyX1": 0,
                "Drużyna2": team2,
                "Kraj2": nat2,
                "PktM2": 0,
                "Minipunkty2": 0,
                "MinipunktyM2": 0,
                "MinipunktyW2": 0,
                "MinipunktyX2": 0,
            })

        df_new = _pd.DataFrame(new_rows, columns=[
            "Runda","Mecz",
            "Drużyna1","Kraj1","PktM1","Minipunkty1","MinipunktyM1","MinipunktyW1","MinipunktyX1",
            "Drużyna2","Kraj2","PktM2","Minipunkty2","MinipunktyM2","MinipunktyW2","MinipunktyX2",
        ])

        # dopisz do istniejących meczów
        df_all = _pd.concat([df_matches, df_new], ignore_index=True)

        out_path = dir_path / "S45_SWISS.csv"
        try:
            df_all.to_csv(out_path, sep=";", index=False, encoding="cp1250")
        except Exception as e:
            messagebox.showerror(
                "SWISS – generowanie",
                f"Nie udało się zapisać S45_SWISS.csv:\n{e}"
            )
            return

        # od razu przeładuj widok rund + tabelę
        try:
            _swiss_reload_matches()
        except Exception:
            pass
        try:
            _swiss_recompute_and_reload_table()
        except Exception:
            pass

        messagebox.showinfo(
            "SWISS – nowa runda",
            f"Wygenerowano rundę {next_round} ({len(pairs)} meczów)\n"
            f"na podstawie aktualnej klasyfikacji."
        )

    def _swiss_reload_matches():
        """Odświeża tabelę rund SWISS na podstawie S45_SWISS.csv."""
        import pandas as _pd
        from pathlib import Path as _Path
        from tkinter import messagebox

        nonlocal tv_swiss_rounds

        if tv_swiss_rounds is None:
            return

        dir_path = _Path(swiss_dir_var.get().strip() or ".")
        try:
            df = _swiss_read_matches_from_dir(dir_path)
        except Exception as e:
            messagebox.showerror("SWISS – rundy", str(e))
            return

        print("[SWISS DEBUG] dir_path:", dir_path)
        print("[SWISS DEBUG] df.shape:", getattr(df, "shape", None))
        print("[SWISS DEBUG] columns:", list(df.columns))

        # wyczyść tabelę
        tv_swiss_rounds.delete(*tv_swiss_rounds.get_children())

        if df is None or df.empty:
            return

        cols = list(tv_swiss_rounds["columns"])
        for _, row in df.iterrows():
            vals = [row.get(c, "") for c in cols_swiss_matches]
            tv_swiss_rounds.insert("", "end", values=vals)

    def _swiss_recompute_and_reload_table():
        """
        Czyta S45_SWISS.csv, przelicza klasyfikację, zapisuje S45_SWISS_Table.csv
        i odświeża tabelę w GUI.
        """
        import pandas as _pd
        from pathlib import Path as _Path
        from tkinter import messagebox

        nonlocal tv_swiss_table, swiss_classif_ft, _swiss_classif_last_df

        if tv_swiss_table is None:
            return

        dir_path = _Path(swiss_dir_var.get().strip() or ".")
        try:
            df_matches = _swiss_read_matches_from_dir(dir_path)
        except Exception as e:
            messagebox.showerror("SWISS – rundy", str(e))
            return

        try:
            df_table = _swiss_compute_table(df_matches)
        except Exception as e:
            messagebox.showerror("SWISS – klasyfikacja", str(e))
            return

        # zapis do CSV
        out_path = dir_path / "S45_SWISS_Table.csv"
        try:
            df_table.to_csv(out_path, sep=";", index=False, encoding="cp1250")
            print(f"[SWISS] Zapisano klasyfikację: {out_path}")
        except Exception as e:
            print("[SWISS] Problem z zapisem tabeli:", e)

        # odśwież tabelę SWISS (FrozenTable: Lp. + Drużyna z flagą)
        if tv_swiss_table is not None:
            if df_table is None or df_table.empty:
                tv_swiss_table.set_dataframe(_pd.DataFrame())
            else:
                tv_swiss_table.set_dataframe(df_table)
                try:
                    tv_swiss_table.autosize()
                except Exception:
                    pass

        if df_table is None or df_table.empty:
            return

        # --- uproszczona klasyfikacja SWISS: Lp., Drużyna, Kraj, Punkty, Finanse, Ranking FIS ---
        if swiss_classif_ft is not None and df_table is not None and not df_table.empty:
            # kopia, żeby nie grzebać w oryginalnej ramce
            df_view = df_table.copy()

            # Punkty = PktM
            if "PktM" in df_view.columns:
                df_view["Punkty"] = _pd.to_numeric(df_view["PktM"], errors="coerce").fillna(0.0)
            else:
                df_view["Punkty"] = 0.0

            # --- Finanse wg miejsca ---
            prize_by_place_swiss = {
                1: 300000, 2: 260000, 3: 230000, 4: 210000, 5: 190000, 6: 180000,
                7: 170000, 8: 160000, 9: 150000, 10: 140000, 11: 135000, 12: 130000,
                13: 125000, 14: 120000, 15: 115000, 16: 110000, 17: 100000, 18: 95000,
                19: 90000, 20: 85000, 21: 80000, 22: 75000, 23: 70000, 24: 65000,
                25: 60000, 26: 58000, 27: 56000, 28: 54000, 29: 52000, 30: 50000,
                31: 48000, 32: 46000, 33: 44000, 34: 42000, 35: 40000, 36: 38000,
                37: 36000, 38: 34000, 39: 32000, 40: 30000, 41: 28000, 42: 26000,
                43: 24000, 44: 23000, 45: 22000, 46: 21000, 47: 20000, 48: 19500,
                49: 19000, 50: 18500, 51: 18000, 52: 17500, 53: 17000, 54: 16500,
                55: 16000, 56: 15500, 57: 15000, 58: 14500, 59: 14000, 60: 13500,
                61: 13000, 62: 12500, 63: 12000, 64: 11500, 65: 11000, 66: 10900,
                67: 10800, 68: 10700, 69: 10600, 70: 10500, 71: 10400, 72: 10300,
                73: 10200, 74: 10100, 75: 10000, 76: 9900, 77: 9800, 78: 9700,
                79: 9600, 80: 9500, 81: 9400, 82: 9300, 83: 9200, 84: 9100,
                85: 9000, 86: 8900, 87: 8800, 88: 8700, 89: 8600, 90: 8500,
                91: 8400, 92: 8300, 93: 8200, 94: 8100, 95: 8000, 96: 7900,
                97: 7800, 98: 7700, 99: 7600, 100: 7500, 101: 7400, 102: 7300,
                103: 7200, 104: 7100, 105: 7000, 106: 6900, 107: 6800, 108: 6700,
                109: 6600, 110: 6500, 111: 6400, 112: 6300, 113: 6200, 114: 6100,
                115: 6000, 116: 5900, 117: 5800, 118: 5700, 119: 5600, 120: 5500,
                121: 5400, 122: 5300, 123: 5200, 124: 5100, 125: 5000, 126: 4900,
                127: 4800, 128: 4700, 129: 4600, 130: 4500, 131: 4400, 132: 4300,
                133: 4200, 134: 4100, 135: 4000, 136: 3900, 137: 3800, 138: 3700,
                139: 3600, 140: 3500, 141: 3400, 142: 3300, 143: 3200, 144: 3100,
                145: 3000, 146: 2900, 147: 2800, 148: 2700, 149: 2600, 150: 2500,
                151: 2400, 152: 2300, 153: 2200, 154: 2100, 155: 2000, 156: 1900,
                157: 1800, 158: 1700, 159: 1600, 160: 1500, 161: 1400, 162: 1300,
                163: 1200, 164: 1100,
            }

            ranking_fis_by_place_swiss = {
                1: 300, 2: 270, 3: 250, 4: 230, 5: 215, 6: 200, 7: 190, 8: 180,
                9: 170, 10: 160, 11: 150, 12: 140, 13: 130, 14: 120, 15: 110, 16: 100,
                17: 95, 18: 90, 19: 85, 20: 80, 21: 76, 22: 72, 23: 68, 24: 64,
                25: 60, 26: 56, 27: 52, 28: 48, 29: 44, 30: 40, 31: 36, 32: 32,
                33: 30, 34: 28, 35: 26, 36: 24, 37: 22, 38: 20, 39: 18, 40: 16,
                41: 14, 42: 12, 43: 10, 44: 8, 45: 6, 46: 4, 47: 2,
            }

            def _place_prize_swiss(p):
                try:
                    p = int(p)
                except Exception:
                    return 0
                return prize_by_place_swiss.get(p, 0)

            def _place_ranking_swiss(p):
                try:
                    p = int(p)
                except Exception:
                    return 0
                if p in ranking_fis_by_place_swiss:
                    return ranking_fis_by_place_swiss[p]
                if 48 <= p <= 64:
                    return 1
                if p >= 65:
                    return 0
                return 0

            # numeric DF do eksportu
            df_export = df_view.copy()
            df_export["Finanse"] = df_export["Lp."].apply(_place_prize_swiss)
            df_export["Ranking FIS"] = df_export["Lp."].apply(_place_ranking_swiss)

            _swiss_classif_last_df = df_export[["Lp.", "Drużyna", "Kraj", "Punkty", "Finanse", "Ranking FIS"]].copy()

            # --- widok do GUI: finansowe z odstępami co 3 cyfry ---
            def _fmt_money(v):
                try:
                    n = int(v)
                except Exception:
                    return ""
                return f"{n:,}".replace(",", " ")

            df_view["Finanse"] = df_export["Finanse"].apply(_fmt_money)
            df_view["Ranking FIS"] = df_export["Ranking FIS"]

            cols_order = ["Lp.", "Drużyna", "Kraj", "Punkty", "Finanse", "Ranking FIS"]
            swiss_classif_ft.set_dataframe(df_view, order=cols_order)
            try:
                swiss_classif_ft.autosize()
            except Exception:
                pass

    def _swiss_export_classif_csv():
        """
        Eksportuje ostatnią klasyfikację SWISS do CSV:
        S45_SWISS_Klasyfikacja.csv w tym samym folderze,
        gdzie jest S45_SWISS_Table.csv (jeśli da się znaleźć).
        """
        import pandas as _pd
        from pathlib import Path as _Path
        from tkinter import messagebox

        nonlocal _swiss_classif_last_df

        if _swiss_classif_last_df is None or _swiss_classif_last_df.empty:
            messagebox.showerror(
                "SWISS",
                "Brak danych klasyfikacji SWISS.\nNajpierw przelicz tabelę."
            )
            return

        # Spróbuj znaleźć tabelę, żeby wziąć folder
        table_path = _find_nearby_file(
            "S45_SWISS_Table.csv",
            alt_patterns=["*SWISS_Table*.csv"]
        )
        if table_path:
            out_dir = _Path(table_path).resolve().parent
        else:
            out_dir = _Path(".").resolve()

        out_path = out_dir / "S45_SWISS_Klasyfikacja.csv"

        try:
            _swiss_classif_last_df.to_csv(
                out_path,
                sep=";",
                encoding="utf-8-sig",
                index=False
            )
        except Exception as e:
            messagebox.showerror(
                "SWISS",
                f"Nie udało się zapisać pliku:\n{e}"
            )
            return

        messagebox.showinfo(
            "SWISS",
            f"Zapisano klasyfikację SWISS:\n{out_path}"
        )

    def _swiss_update_from_results(comp_label: str):
        """
        Uzupełnia WSZYSTKIE mecze z danej rundy SWISS na podstawie
        ostatniego konkursu TEAM (global _LAST_TEAM_CLASSIF).

        comp_label:
          - 'MEN'   -> MinipunktyM
          - 'WOMEN' -> MinipunktyW
          - 'MIXED' -> MinipunktyX
        """
        import pandas as pd
        from pathlib import Path as _Path
        from tkinter import messagebox

        nonlocal tv_swiss_rounds

        df_res = globals().get("_LAST_TEAM_CLASSIF", None)
        if df_res is None or getattr(df_res, "empty", True):
            messagebox.showwarning(
                "SWISS – wyniki",
                "Brak wyników drużynowych w pamięci.\n"
                "Najpierw uruchom konkurs TEAM w głównej zakładce."
            )
            return

        comp_label = str(comp_label or "").upper().strip()
        if comp_label in ("M", "MEN"):
            comp_code = "M"
            mini_col_prefix = "MinipunktyM"
            human = "MEN"
        elif comp_label in ("W", "WOMEN"):
            comp_code = "W"
            mini_col_prefix = "MinipunktyW"
            human = "WOMEN"
        else:
            # MIX / MIXED / cokolwiek innego → MIXED
            comp_code = "X"
            mini_col_prefix = "MinipunktyX"
            human = "MIXED"

        # kolumny w wynikach TEAM
        nat_col = next((c for c in ["Kraj", "NAT", "KRAJ", "Country", "TeamNat"] if c in df_res.columns), None)
        pts_col = next((c for c in ["Punkty", "Suma", "Punkty drużyny"] if c in df_res.columns), None)

        if not nat_col or not pts_col:
            messagebox.showerror(
                "SWISS – wyniki",
                "Nie znalazłem kolumn 'Kraj/NAT' i/lub 'Punkty' w wynikach drużyn.\n"
                "Sprawdź, czy tabela TEAM ma odpowiednie nagłówki."
            )
            return

        tmp = df_res[[nat_col, pts_col]].copy()
        tmp[nat_col] = tmp[nat_col].astype(str).str.upper().str.strip()
        tmp[pts_col] = pd.to_numeric(tmp[pts_col], errors="coerce").fillna(0.0)
        pts_map = tmp.groupby(nat_col, dropna=False)[pts_col].sum().to_dict()

        # wybór JEDNEGO meczu – ale tylko po to, żeby wziąć numer rundy
        if tv_swiss_rounds is None:
            messagebox.showerror("SWISS – rundy", "Tabela rund SWISS nie jest gotowa.")
            return

        sel = tv_swiss_rounds.selection()
        if not sel:
            messagebox.showinfo(
                "SWISS – wyniki",
                "Zaznacz najpierw dowolny mecz w wybranej rundzie."
            )
            return

        if len(sel) > 1:
            sel = sel[:1]  # bierzemy pierwszy, reszta nas nie interesuje

        cols = list(tv_swiss_rounds["columns"])
        row_vals = tv_swiss_rounds.item(sel[0], "values") or []
        row = {c: (row_vals[i] if i < len(row_vals) else "") for i, c in enumerate(cols)}

        try:
            runda = int(float(str(row.get("Runda", "0")).replace(",", ".")))
        except Exception:
            runda = None

        if not runda:
            messagebox.showerror(
                "SWISS – wyniki",
                "Nie udało się odczytać numeru rundy z zaznaczonego wiersza."
            )
            return

        # wczytaj pełny S45_SWISS.csv
        dir_path = _Path(swiss_dir_var.get().strip() or ".")
        p = dir_path / "S45_SWISS.csv"
        if not p.is_file():
            messagebox.showerror("SWISS – wyniki", f"Brak pliku S45_SWISS.csv w folderze:\n{dir_path}")
            return

        df = _swiss_read_matches_from_dir(dir_path)
        if df is None or df.empty:
            messagebox.showerror("SWISS – wyniki", "Plik S45_SWISS.csv jest pusty lub uszkodzony.")
            return

        # wybierz wszystkie mecze z danej rundy
        mask_round = df["Runda"] == runda
        idx_round = df.index[mask_round]

        if len(idx_round) == 0:
            messagebox.showerror(
                "SWISS – wyniki",
                f"Nie znalazłem żadnych meczów w rundzie {runda} w S45_SWISS.csv."
            )
            return

        updated = 0
        skipped = []

        for i in idx_round:
            nat1 = str(df.at[i, "Kraj1"]).strip().upper() if "Kraj1" in df.columns else ""
            nat2 = str(df.at[i, "Kraj2"]).strip().upper() if "Kraj2" in df.columns else ""

            if not nat1 or not nat2:
                skipped.append((nat1 or "?", nat2 or "?"))
                continue

            if nat1 not in pts_map or nat2 not in pts_map:
                skipped.append((nat1, nat2))
                continue

            mini1 = round(float(pts_map.get(nat1, 0.0)), 1)
            mini2 = round(float(pts_map.get(nat2, 0.0)), 1)

            # przelicz PktM: wygrana 2, remis 1–1, przegrana 0
            if abs(mini1 - mini2) < 1e-6:
                add1 = add2 = 1.0
            elif mini1 > mini2:
                add1, add2 = 2.0, 0.0
            else:
                add1, add2 = 0.0, 2.0

            # uaktualnij MinipunktyM/W/X
            df.at[i, f"{mini_col_prefix}1"] = float(mini1)
            df.at[i, f"{mini_col_prefix}2"] = float(mini2)

            # uaktualnij PktM1/2 (dodajemy do istniejących)
            for side, add in (("1", add1), ("2", add2)):
                col = f"PktM{side}"
                try:
                    old = float(df.at[i, col] or 0.0)
                except Exception:
                    old = 0.0
                df.at[i, col] = old + add

            # przelicz Minipunkty1/2 = suma M+W+X dla tego wiersza (zaokrąglone do 0.1)
            for side in ("1", "2"):
                total_mini = (
                    float(df.at[i, f"MinipunktyM{side}"] or 0.0)
                    + float(df.at[i, f"MinipunktyW{side}"] or 0.0)
                    + float(df.at[i, f"MinipunktyX{side}"] or 0.0)
                )
                df.at[i, f"Minipunkty{side}"] = round(total_mini, 1)


            updated += 1

        # zapisz do CSV
        try:
            df.to_csv(p, sep=";", index=False, encoding="cp1250")
        except Exception:
            df.to_csv(p, sep=";", index=False, encoding="utf-8-sig")

        # odśwież GUI
        try:
            _swiss_reload_matches()
        except Exception:
            pass
        try:
            _swiss_recompute_and_reload_table()
        except Exception:
            pass

        msg = f"Zaktualizowano rundę {runda} dla typu {human}.\n" \
              f"Mecze zaktualizowane: {updated}"
        if skipped:
            # nie będę tu robił elaboratu, tylko krótkie info
            msg += f"\nPominięte mecze (brak wyników dla krajów): {len(skipped)}"

        messagebox.showinfo("SWISS – wyniki", msg)

    # --- SWISS: automatyczne odświeżenie przy starcie GUI ---
    try:
        _swiss_reload_matches()
    except Exception as e:
        print("[SWISS] auto-reload przy starcie nieudany:", e)

    try:
        _swiss_recompute_and_reload_table()
    except Exception as e:
        print("[SWISS] auto-reload tabeli przy starcie nieudany:", e)

    # --- FALLS: kompatybilny wrapper, żeby działały stare i nowe wywołania ---
    def _build_falls_sheet_compat(df1, df2=None):
        import inspect
        import pandas as _pd
        try:
            from team_competition_display2rows_v3_fix import build_falls_sheet as _falls_orig
        except Exception:
            # awaryjnie bez oryginału: zwróć pustą ramkę zamiast wysadzić GUI
            return _pd.DataFrame(columns=["Runda","Zawodnik","Kraj","Upadek","Odległość (m)","Noty stylowe"])

        # jeśli mamy dwie rundy – zlepiamy; jeśli jedna – bierzemy jedną
        df_all = df1
        if df2 is not None and hasattr(df2, "empty") and not df2.empty:
            try:
                df_all = _pd.concat([df1, df2], ignore_index=True)
            except Exception:
                df_all = df1

        # wykryj sygnaturę oryginału (nowa: 1 arg)
        try:
            sig = inspect.signature(_falls_orig)
            if len(sig.parameters) <= 1:
                return _falls_orig(df_all)
            else:
                # stary wariant (2 arg) – podaj oba
                return _falls_orig(df1, df2)
        except Exception:
            # na wszelki wypadek spróbuj jednej rundy
            try:
                return _falls_orig(df_all)
            except Exception:
                return _pd.DataFrame(columns=["Runda","Zawodnik","Kraj","Upadek","Odległość (m)","Noty stylowe"])

    try:
        _load_hills_csv_team()
    except Exception:
        pass

    def _team_update_nations_from_results(season: str, cycle: str, is_mix: bool = False):
        """
        Pancerna aktualizacja klasyfikacji: zachowuje kolumnę I, 
        dodaje punkty FIS do T i naprawia uszkodzone pliki.
        """
        import pandas as pd
        from pathlib import Path
        from tkinter import messagebox

        # 1. Pobranie wyników
        df_results = globals().get("_LAST_TEAM_CLASSIF", None)
        if df_results is None or getattr(df_results, "empty", True):
            messagebox.showwarning("Błąd", "Brak wyników w pamięci. Uruchom najpierw zawody.")
            return

        # Ustalenie kolumn źródłowych
        nat_col_src = next((c for c in ["NAT", "Kraj", "KRAJ"] if c in df_results.columns), "Kraj")
        
        # Mapa punktów FIS (szukamy 400, 350...)
        fis_scale = {1: 400, 2: 350, 3: 300, 4: 250, 5: 200, 6: 150, 7: 100, 8: 50}
        
        def calculate_points(row):
            # Próba pobrania gotowych punktów FIS
            for c in ["Punkty FIS", "Punkty FIS (TEAM)"]:
                if c in df_results.columns:
                    val = pd.to_numeric(row[c], errors="coerce")
                    if not pd.isna(val) and val > 0: return val
            # Fallback: obliczanie po miejscu
            for c in ["Miejsce", "LP.", "Rank"]:
                if c in df_results.columns:
                    r = pd.to_numeric(row[c], errors="coerce")
                    if not pd.isna(r): return fis_scale.get(int(r), 0)
            return 0

        # Przygotowanie danych do dodania
        results_to_add = df_results.copy()
        results_to_add["NAT_KEY"] = results_to_add[nat_col_src].astype(str).str.upper().str.strip()
        results_to_add["FIS_TO_ADD"] = results_to_add.apply(calculate_points, axis=1)
        if is_mix: results_to_add["FIS_TO_ADD"] *= 0.5

        # 2. Wczytanie pliku klasyfikacji
        cls_dir = Path(f"./{season}/Klasyfikacje {season}")
        cls_dir.mkdir(parents=True, exist_ok=True)
        nations_path = cls_dir / f"{season}_{cycle}__nations.csv"
        required_cols = ["LP.", "NATION", "NAT", "T", "I", "PTS", "1", "2", "3"]

        if nations_path.exists():
            try:
                # Próba wczytania z różnymi separatorami
                dfN = pd.read_csv(nations_path, sep=";", engine="python", encoding="utf-8-sig")
                if len(dfN.columns) < 3:
                    dfN = pd.read_csv(nations_path, sep=",", engine="python", encoding="utf-8-sig")
            except:
                dfN = pd.DataFrame(columns=required_cols)
        else:
            dfN = pd.DataFrame(columns=required_cols)

        # --- RATOWANIE PLIKU: Usuwanie błędnych wierszy '0;0;0' ---
        if not dfN.empty:
            # Usuwamy wszystko co nie ma poprawnego kodu państwa (min. 2 litery)
            dfN = dfN[dfN["NAT"].astype(str).str.strip().str.len() >= 2].copy()

        # Zapewnienie poprawności typów (zachowanie istniejących wartości I)
        for col in required_cols:
            if col not in dfN.columns: dfN[col] = 0
            if col in ["T", "I", "PTS", "1", "2", "3"]:
                dfN[col] = pd.to_numeric(dfN[col], errors="coerce").fillna(0)

        dfN["NAT"] = dfN["NAT"].astype(str).str.upper().str.strip()

        # 3. Aktualizacja
        for _, res_row in results_to_add.iterrows():
            nat = res_row["NAT_KEY"]
            pts = res_row["FIS_TO_ADD"]
            rank = pd.to_numeric(res_row.get("Miejsce", 0), errors="coerce")

            if nat in dfN["NAT"].values:
                # Aktualizacja istniejącego kraju (I zostaje bez zmian!)
                dfN.loc[dfN["NAT"] == nat, "T"] += float(pts)
                if rank in [1, 2, 3]:
                    dfN.loc[dfN["NAT"] == nat, str(int(rank))] += 1
            else:
                # Dodanie nowego kraju (I inicjowane na 0)
                full_name = TEAM_NAME.get(nat, nat)
                new_data = {c: 0 for c in required_cols}
                new_data.update({
                    "NATION": full_name, "NAT": nat, "T": float(pts),
                    str(int(rank)) if rank in [1, 2, 3] else "LP.": 1 if rank in [1, 2, 3] else 0
                })
                dfN = pd.concat([dfN, pd.DataFrame([new_data])], ignore_index=True)

        # 4. Finalne przeliczenie i porządkowanie
        dfN["PTS"] = dfN["T"] + dfN["I"]
        dfN = dfN.sort_values(by=["PTS", "1", "2", "3"], ascending=False).reset_index(drop=True)
        dfN["LP."] = range(1, len(dfN) + 1)

        # Konwersja statystyk na liczby całkowite
        for c in ["1", "2", "3", "I"]:
            if c == "I": # I może być floatem jeśli masz punkty z ułamkiem, ale zazwyczaj to int
                continue 
            dfN[c] = dfN[c].astype(int)

        # 5. Zapis
        try:
            dfN[required_cols].to_csv(nations_path, index=False, sep=";", encoding="utf-8-sig")
            messagebox.showinfo("Sukces", f"Klasyfikacja zaktualizowana.\nKolumna I została zachowana, punkty FIS dodane do T.")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Nie można zapisać pliku: {e}")
            
    def _cc_update_groups_from_results(kolejka: int):
        """
        Aktualizuje S45_CC_Grupa_A…D.csv na podstawie:
        - terminarza grup CC (kolejka 1–3),
        - ostatniego konkursu drużyn (_LAST_TEAM_CLASSIF).

        Dla każdej pary z terminarza:
        - zwycięzca: +1 'Punkty Zdobyte'
        - przegrany: +1 'Punkty Stracone'
        - oba zespoły dostają do 'Minipunkty' swoje punkty z konkursu.
        """
        from tkinter import messagebox
        from pathlib import Path
        import pandas as pd

        # --- walidacja kolejki ---
        try:
            k = int(kolejka)
        except Exception:
            messagebox.showwarning("CC – grupy", "Nieprawidłowa kolejka CC.")
            return

        if k not in (1, 2, 3):
            messagebox.showwarning("CC – grupy", "Kolejka CC musi być 1, 2 albo 3.")
            return

        # --- wyniki drużyn z ostatniego konkursu ---
        df_res = globals().get("_LAST_TEAM_CLASSIF", None)
        if df_res is None or getattr(df_res, "empty", True):
            messagebox.showwarning(
                "CC – grupy",
                "Brak wyników drużynowych w pamięci.\n"
                "Uruchom konkurs TEAM dla wszystkich drużyn z grup CC i spróbuj ponownie."
            )
            return

        try:
            dfr = pd.DataFrame(df_res).copy()
        except Exception:
            messagebox.showerror("CC – grupy", "Nie mogę zinterpretować ostatniej klasyfikacji drużyn.")
            return

        if "Kraj" not in dfr.columns or "Punkty" not in dfr.columns:
            messagebox.showerror(
                "CC – grupy",
                "Ostatnia klasyfikacja drużyn nie ma kolumn 'Kraj' i 'Punkty'."
            )
            return

        dfr["Kraj"] = dfr["Kraj"].astype(str).str.strip().str.upper()
        dfr["Punkty"] = pd.to_numeric(dfr["Punkty"], errors="coerce").fillna(0.0)
        pts_map = dict(zip(dfr["Kraj"], dfr["Punkty"]))

        # --- terminarz CC z aktualnych grup w GUI ---
        groups = _cc_collect_groups()
        if not groups:
            messagebox.showwarning(
                "CC – grupy",
                "Brak aktualnych grup CC. Najpierw wylosuj/wczytaj grupy w zakładce CC."
            )
            return

        schedule_list = _cc_build_group_schedule(groups)
        if not schedule_list:
            messagebox.showwarning("CC – grupy", "Brak terminarza CC.")
            return

        matches = [row for row in schedule_list if int(row.get("Kolejka", 0)) == k]
        if not matches:
            messagebox.showwarning("CC – grupy", f"Brak meczów dla kolejki {k}.")
            return

        # --- wczytanie tabel grup z plików ---
        dir_path = Path(cc_dir_var.get().strip() or ".")
        if not dir_path.is_dir():
            messagebox.showerror("CC – grupy", f"Folder CC nie istnieje:\n{dir_path}")
            return

        group_tables: dict[str, pd.DataFrame] = {}
        needed_cols = ["Lp.", "Drużyna", "Kraj", "Punkty Zdobyte", "Punkty Stracone", "Minipunkty"]

        for g in sorted(groups.keys()):
            p = dir_path / f"S45_CC_Grupa_{g}.csv"
            if not p.is_file():
                continue
            try:
                df_g = _cc_read_q_csv_any(p)
            except Exception as e:
                print("CC update: błąd wczytywania", p, "->", e)
                continue

            for col in needed_cols:
                if col not in df_g.columns:
                    if col in ("Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
                        df_g[col] = 0
                    else:
                        df_g[col] = ""

            df_g["Kraj"] = df_g["Kraj"].astype(str).str.strip().str.upper()
            for col in ("Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
                df_g[col] = pd.to_numeric(df_g[col], errors="coerce").fillna(0.0)

            group_tables[g] = df_g

        if not group_tables:
            messagebox.showwarning(
                "CC – grupy",
                "Nie znaleziono żadnych plików S45_CC_Grupa_*.csv do aktualizacji."
            )
            return

        # --- aktualizacja wg meczów ---
        skipped: list[str] = []

        for row in matches:
            g = str(row.get("Grupa", "")).strip()
            nat1 = str(row.get("Kraj1", "")).strip().upper()
            nat2 = str(row.get("Kraj2", "")).strip().upper()

            if not g or not nat1 or not nat2:
                continue
            if g not in group_tables:
                skipped.append(f"{g}: {nat1}-{nat2} (brak tabeli grupy)")
                continue

            df_g = group_tables[g]
            p1 = pts_map.get(nat1)
            p2 = pts_map.get(nat2)

            if p1 is None or p2 is None:
                skipped.append(f"{g}: {nat1}-{nat2} (brak wyników dla jednej z drużyn)")
                continue

            mask1 = df_g["Kraj"].eq(nat1)
            mask2 = df_g["Kraj"].eq(nat2)

            if not mask1.any() or not mask2.any():
                skipped.append(f"{g}: {nat1}-{nat2} (brak w tabeli grupy)")
                continue

            # Minipunkty = suma punktów z konkursów
            df_g.loc[mask1, "Minipunkty"] = df_g.loc[mask1, "Minipunkty"].astype(float) + float(p1)
            df_g.loc[mask2, "Minipunkty"] = df_g.loc[mask2, "Minipunkty"].astype(float) + float(p2)

            # Punkty zdobyte / stracone
            if p1 > p2:
                df_g.loc[mask1, "Punkty Zdobyte"] = df_g.loc[mask1, "Punkty Zdobyte"].astype(float) + 1
                df_g.loc[mask2, "Punkty Stracone"] = df_g.loc[mask2, "Punkty Stracone"].astype(float) + 1
            elif p2 > p1:
                df_g.loc[mask2, "Punkty Zdobyte"] = df_g.loc[mask2, "Punkty Zdobyte"].astype(float) + 1
                df_g.loc[mask1, "Punkty Stracone"] = df_g.loc[mask1, "Punkty Stracone"].astype(float) + 1
            # remis -> nic z punktami Z/S

            group_tables[g] = df_g

        # --- zapis z powrotem do CSV (sortowanie + zaokrąglenie) ---
        for g, df_g in group_tables.items():
            p = dir_path / f"S45_CC_Grupa_{g}.csv"

            # dopilnujmy typów numerycznych
            for col in ("Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
                df_g[col] = pd.to_numeric(df_g[col], errors="coerce").fillna(0.0)

            # zaokrąglenie Minipunktów do 1 miejsca po przecinku
            df_g["Minipunkty"] = df_g["Minipunkty"].round(1)

            # sortowanie: najpierw Punkty Zdobyte, potem Minipunkty (oba malejąco)
            df_g = df_g.sort_values(
                by=["Punkty Zdobyte", "Minipunkty"],
                ascending=[False, False],
                kind="mergesort"  # stabilne sortowanie
            ).reset_index(drop=True)

            # odśwież Lp. po posortowaniu
            df_g["Lp."] = range(1, len(df_g) + 1)

            # zachowujemy kolejność kolumn
            df_out = df_g[needed_cols].copy()

            try:
                df_out.to_csv(p, sep=";", encoding="cp1250", index=False)
            except Exception:
                df_out.to_csv(p, sep=";", encoding="utf-8-sig", index=False)

        # --- odśwież GUI grup CC ---
        try:
            _cc_groups_reload()
        except Exception:
            pass

        msg = f"Zaktualizowano tabele grup CC dla kolejki {k}."
        if skipped:
            msg += "\n\nUwaga, pominięte mecze:\n- " + "\n- ".join(skipped[:10])
            if len(skipped) > 10:
                msg += f"\n(+{len(skipped) - 10} kolejnych...)"
        messagebox.showinfo("CC – grupy", msg)

    def _cc_update_bracket_from_results(faza: str):
        """
        Aktualizuje drabinkę pucharową CC na podstawie:
        - S45_CC_Puchar.csv
        - ostatniej klasyfikacji drużyn (_LAST_TEAM_CLASSIF)

        Zasady:
        - zwycięzca meczu: +1 w kolumnie Punkty1/Punkty2
        - Minipunkty1/2: dodawane punkty drużyny z konkursu
        """
        from tkinter import messagebox
        from pathlib import Path
        import pandas as pd

        faza = str(faza).strip()

        phase_map = {
            "1/4": ["M1", "M2", "M3", "M4", "M13", "M14", "M17", "M18"],
            "1/2": ["M5", "M6", "M9", "M10", "M15", "M16", "M19", "M20"],
            "Finał": ["M7", "M8", "M11", "M12"],
        }

        if faza not in phase_map:
            messagebox.showwarning("CC – puchar", "Wybierz fazę: 1/4, 1/2 lub Finał.")
            return

        # --- wyniki drużyn z ostatniego konkursu ---
        df_res = globals().get("_LAST_TEAM_CLASSIF", None)
        if df_res is None or getattr(df_res, "empty", True):
            messagebox.showwarning(
                "CC – puchar",
                "Brak wyników drużynowych w pamięci.\n"
                "Uruchom konkurs TEAM dla wszystkich drużyn i spróbuj ponownie."
            )
            return

        try:
            dfr = pd.DataFrame(df_res).copy()
        except Exception:
            messagebox.showerror("CC – puchar", "Nie mogę zinterpretować ostatniej klasyfikacji drużyn.")
            return

        if "Kraj" not in dfr.columns or "Punkty" not in dfr.columns:
            messagebox.showerror(
                "CC – puchar",
                "Ostatnia klasyfikacja drużyn nie ma kolumn 'Kraj' i 'Punkty'."
            )
            return

        dfr["Kraj"] = dfr["Kraj"].astype(str).str.strip().str.upper()
        dfr["Punkty"] = pd.to_numeric(dfr["Punkty"], errors="coerce").fillna(0.0)
        pts_map = dict(zip(dfr["Kraj"], dfr["Punkty"]))

        # --- wczytanie pliku pucharowego ---
        dir_path = Path(cc_dir_var.get().strip() or ".")
        if not dir_path.is_dir():
            messagebox.showerror("CC – puchar", f"Folder CC nie istnieje:\n{dir_path}")
            return

        p = dir_path / "S45_CC_Puchar.csv"
        if not p.is_file():
            messagebox.showwarning("CC – puchar", f"Brak pliku pucharu:\n{p}")
            return

        try:
            df = _cc_read_q_csv_any(p)
        except Exception as e:
            messagebox.showerror("CC – puchar", f"Błąd wczytywania pliku pucharu:\n{e}")
            return

        needed_cols = [
            "Mecz", "Faza",
            "Drużyna1", "Kraj1", "Punkty1", "Minipunkty1",
            "Drużyna2", "Kraj2", "Punkty2", "Minipunkty2",
        ]
        for col in needed_cols:
            if col not in df.columns:
                df[col] = 0 if col.startswith(("Punkty", "Minipunkty")) else ""

        for col in ("Punkty1", "Punkty2", "Minipunkty1", "Minipunkty2"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        df["Kraj1"] = df["Kraj1"].astype(str).str.strip().str.upper()
        df["Kraj2"] = df["Kraj2"].astype(str).str.strip().str.upper()

        target_matches = set(phase_map[faza])
        skipped: list[str] = []

        # --- aktualizacja meczów z danej fazy ---
        for idx, row in df.iterrows():
            mecz_id = str(row.get("Mecz", "")).strip()
            if mecz_id not in target_matches:
                continue

            nat1 = row["Kraj1"]
            nat2 = row["Kraj2"]
            if not nat1 or not nat2:
                skipped.append(f"{mecz_id}: brak krajów")
                continue

            p1 = pts_map.get(nat1)
            p2 = pts_map.get(nat2)

            if p1 is None or p2 is None:
                skipped.append(f"{mecz_id}: brak wyników dla {nat1} lub {nat2}")
                continue

            # Minipunkty – sumujemy punkty z konkursu
            df.at[idx, "Minipunkty1"] = float(df.at[idx, "Minipunkty1"]) + float(p1)
            df.at[idx, "Minipunkty2"] = float(df.at[idx, "Minipunkty2"]) + float(p2)

            # Punkty meczu – 1 za zwycięstwo
            if p1 > p2:
                df.at[idx, "Punkty1"] = float(df.at[idx, "Punkty1"]) + 1.0
            elif p2 > p1:
                df.at[idx, "Punkty2"] = float(df.at[idx, "Punkty2"]) + 1.0
            # remis: bez zmian

        # --- zaokrąglenie Minipunktów do 1 miejsca po przecinku ---
        df["Minipunkty1"] = df["Minipunkty1"].round(1)
        df["Minipunkty2"] = df["Minipunkty2"].round(1)

        # --- zapis z powrotem ---
        df_out = df[needed_cols].copy()
        try:
            df_out.to_csv(p, sep=";", encoding="cp1250", index=False)
        except Exception:
            df_out.to_csv(p, sep=";", encoding="utf-8-sig", index=False)

        msg = f"Zaktualizowano drabinkę pucharową CC dla fazy {faza}."
        if skipped:
            msg += "\n\nPominięte mecze:\n- " + "\n- ".join(skipped[:10])
            if len(skipped) > 10:
                msg += f"\n(+{len(skipped) - 10} kolejnych...)"
        messagebox.showinfo("CC – puchar", msg)

    def _msc_update_group(sex: str, group_no: int):
        try:
            # 1. Mapujemy numer na literę grupy (1->A, 2->B, 3->C, 4->D)
            group_map = {1: "A", 2: "B", 3: "C", 4: "D"}
            group_letter = group_map.get(group_no, "A")
            
            # 2. Tworzymy poprawną nazwę pliku (np. S45_MSC_W_Grupa_A.csv)
            filename = f"S45_MSC_{sex}_Grupa_{group_letter}.csv"
            
            # 3. Szukamy pliku w dostępnych lokalizacjach
            path = _find_nearby_file(filename)
            
            if not path:
                # Próba awaryjna: sprawdźmy, czy plik nie ma nazwy z numerem zamiast litery
                path = _find_nearby_file(f"S45_MSC_{sex}_Grupa_{group_no}.csv")

            if not path:
                messagebox.showwarning("MSC", f"Nie znaleziono pliku: {filename}\nUpewnij się, że plik znajduje się w folderze MSC.")
                return
                
            df = _read_tab_any(path)
            if df is None:
                messagebox.showwarning("MSC", f"Nie można odczytać zawartości pliku: {path}")
                return

            # 4. Aktualizacja tabeli w odpowiedniej zakładce GUI
            # Uwaga: msc_groups to słownik przechowujący obiekty FrozenTable
            if sex == "M":
                msc_groups["M"][group_letter].set_dataframe(df)
            else:
                msc_groups["W"][group_letter].set_dataframe(df)

            messagebox.showinfo("MSC", f"Zaktualizowano tabelę grupy {group_letter} ({sex}) na podstawie pliku.")
        except Exception as e:
            messagebox.showerror("MSC", f"Wystąpił błąd podczas aktualizacji: {e}")
            
    def _msc_update_all_groups_from_results(sex: str, runda: str):
        """
        Aktualizuje pliki S45_MSC_<sex>_Grupa_A...D.csv na podstawie:
        - terminarza MSC dla danej płci,
        - ostatniego konkursu drużynowego (_LAST_TEAM_CLASSIF).
        """
        import pandas as pd
        from pathlib import Path
        from tkinter import messagebox

        # 1. Pobierz wyniki z ostatniego konkursu
        df_res = globals().get("_LAST_TEAM_CLASSIF", None)
        if df_res is None or df_res.empty:
            messagebox.showwarning("MSC", "Brak wyników w pamięci. Uruchom konkurs TEAM.")
            return

        # Przygotuj mapę punktów: Kraj -> Punkty
        dfr = df_res.copy()
        dfr["Kraj"] = dfr["Kraj"].astype(str).str.strip().str.upper()
        pts_map = dict(zip(dfr["Kraj"], dfr["Punkty"]))

        # 2. Pobierz terminarz dla danej płci
        try:
            # Wykorzystujemy istniejącą logikę zbierania grup i budowania terminarza
            groups_dict = _msc_collect_groups(sex)
            full_schedule = _cc_build_group_schedule(groups_dict)
            # Filtrujemy mecze tylko dla wybranej kolejki (runda)
            current_matches = [m for m in full_schedule if str(m.get("Kolejka")) == str(runda)]
        except Exception as e:
            messagebox.showerror("MSC", f"Błąd terminarza: {e}")
            return

        if not current_matches:
            messagebox.showwarning("MSC", f"Brak meczów w terminarzu dla kolejki {runda}.")
            return

        # 3. Ścieżka do plików (zależna od płci)
        dir_var = self.msc_m_dir_var if sex == "M" else self.msc_w_dir_var
        dir_path = Path(dir_var.get().strip() or ".")

        updated_groups = set()
        
        # 4. Proces aktualizacji plików dla każdej grupy
        for g_letter in ("A", "B", "C", "D"):
            filename = f"S45_MSC_{sex}_Grupa_{g_letter}.csv"
            path = dir_path / filename
            
            if not path.exists():
                continue

            try:
                df_g = _read_tab_any(path)
                if df_g is None: continue
                
                # Normalizacja kolumn
                df_g["Kraj"] = df_g["Kraj"].astype(str).str.strip().str.upper()
                for col in ("Punkty Zdobyte", "Punkty Stracone", "Minipunkty"):
                    df_g[col] = pd.to_numeric(df_g[col], errors="coerce").fillna(0.0)

                # Filtrujemy mecze tylko dla tej konkretnej grupy
                group_matches = [m for m in current_matches if m.get("Grupa") == g_letter]

                for match in group_matches:
                    nat1, nat2 = match["Kraj1"].upper(), match["Kraj2"].upper()
                    p1 = pts_map.get(nat1) # Punkty Japonii (447.8)
                    p2 = pts_map.get(nat2) # Punkty Kazachstanu (1007.8)

                    if p1 is not None and p2 is not None:
                        # Dodaj Minipunkty (punkty ze skoków) do tabeli
                        df_g.loc[df_g["Kraj"] == nat1, "Minipunkty"] += p1
                        df_g.loc[df_g["Kraj"] == nat2, "Minipunkty"] += p2
                        
                        # LOGIKA PKT MECZOWYCH (Korekta):
                        if p1 > p2:
                            # Drużyna 1 wygrywa
                            df_g.loc[df_g["Kraj"] == nat1, "Punkty Zdobyte"] += 1
                            df_g.loc[df_g["Kraj"] == nat2, "Punkty Stracone"] += 1
                        elif p2 > p1:
                            # Drużyna 2 wygrywa (Tutaj powinien trafić Kazachstan)
                            df_g.loc[df_g["Kraj"] == nat2, "Punkty Zdobyte"] += 1
                            df_g.loc[df_g["Kraj"] == nat1, "Punkty Stracone"] += 1
                        else:
                            # Remis (opcjonalnie, w MSC rzadko spotykane)
                            pass

                # Zapisz i odśwież widok
                df_g = df_g.sort_values(["Punkty Zdobyte", "Minipunkty"], ascending=False)
                df_g["Lp."] = range(1, len(df_g) + 1)
                df_g.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
                updated_groups.add(g_letter)

            except Exception as e:
                print(f"Błąd grupy {g_letter}: {e}")

        # 5. Odśwież tabele w GUI
        _msc_groups_reload(sex)
        messagebox.showinfo("MSC", f"Zaktualizowano grupy: {', '.join(sorted(updated_groups))} ({sex})")
        
    _MSC_KNOCKOUT_MAP = {
        "QF":  [1,2,3,4,13,14,17,18],   # 1/4 finału
        "SF":  [5,6,9,10,15,16,19,20], # 1/2 finału
        "F":   [7,8,11,12],            # Finał
    }

    def _msc_update_knockout(sex: str, phase_key: str):
        import pandas as pd
        from pathlib import Path
        from tkinter import messagebox

        # 1. Pobieranie wyników z pamięci
        df_res = globals().get("_LAST_TEAM_CLASSIF", None)
        if df_res is None or df_res.empty:
            messagebox.showwarning("MSC", "Brak wyników w pamięci. Uruchom konkurs TEAM.")
            return

        pts_map = dict(zip(df_res["Kraj"].str.upper(), df_res["Punkty"]))

        # 2. Lokalizacja pliku
        dir_var = self.msc_m_dir_var if sex == "M" else self.msc_w_dir_var
        dir_path = Path(dir_var.get().strip() or ".")
        season = dir_path.parent.name if "S" in dir_path.parent.name else "S45"
        path = dir_path / f"{season}_MSC_{sex}_Puchar.csv"

        if not path.exists():
            messagebox.showwarning("MSC", f"Brak pliku: {path}")
            return

        # 3. Bezpieczne wczytywanie (Naprawa błędu UnicodeDecodeError)
        df = None
        for enc in ["utf-8-sig", "cp1250", "utf-8", "latin-1"]:
            try:
                df = pd.read_csv(path, sep=";", encoding=enc)
                break
            except:
                continue

        if df is None:
            messagebox.showerror("Błąd", "Nie można odczytać pliku CSV.")
            return

        # 4. Harmonogram meczów
        phase_matches = {
            "QF": ["M1", "M2", "M3", "M4", "M13", "M14", "M17", "M18"],
            "SF": ["M5", "M6", "M9", "M10", "M15", "M16", "M19", "M20"],
            "F":  ["M7", "M8", "M11", "M12"]
        }
        
        target_ids = phase_matches.get(phase_key, [])
        winners, losers = {}, {}

        # 5. Aktualizacja punktów i wyłanianie zwycięzców
        for idx, row in df.iterrows():
            m_id = str(row["Mecz"]).strip()
            if m_id in target_ids:
                n1, n2 = str(row["Kraj1"]).upper(), str(row["Kraj2"]).upper()
                p1, p2 = pts_map.get(n1, 0), pts_map.get(n2, 0)
                
                df.at[idx, "Punkty1"] = p1
                df.at[idx, "Punkty2"] = p2
                
                if p1 > p2:
                    winners[m_id] = (row["Drużyna1"], row["Kraj1"])
                    losers[m_id]  = (row["Drużyna2"], row["Kraj2"])
                else:
                    winners[m_id] = (row["Drużyna2"], row["Kraj2"])
                    losers[m_id]  = (row["Drużyna1"], row["Kraj1"])

        # 6. Logika awansów (helper)
        def _fill(target_mid, slot, source_mid, result_type='W'):
            source_data = winners if result_type == 'W' else losers
            if source_mid in source_data:
                t_idx_list = df[df["Mecz"] == target_mid].index
                if not t_idx_list.empty:
                    t_idx = t_idx_list[0]
                    df.at[t_idx, f"Drużyna{slot}"] = source_data[source_mid][0]
                    df.at[t_idx, f"Kraj{slot}"] = source_data[source_mid][1]

        # Realizacja awansów zgodnie z Twoją prośbą o mecze równoległe
        if phase_key == "QF":
            # Awanse do głównej drabinki i dolnych finałów
            _fill("M5", "1", "M1", 'W'); _fill("M5", "2", "M2", 'W')
            _fill("M6", "1", "M3", 'W'); _fill("M6", "2", "M4", 'W')
            _fill("M9", "1", "M1", 'L'); _fill("M9", "2", "M2", 'L')
            _fill("M10", "1", "M3", 'L'); _fill("M10", "2", "M4", 'L')
            _fill("M15", "1", "M13", 'W'); _fill("M15", "2", "M14", 'W')
            _fill("M16", "1", "M13", 'L'); _fill("M16", "2", "M14", 'L')
            _fill("M19", "1", "M17", 'W'); _fill("M19", "2", "M18", 'W')
            _fill("M20", "1", "M17", 'L'); _fill("M20", "2", "M18", 'L')

        elif phase_key == "SF":
            _fill("M7", "1", "M5", 'W'); _fill("M7", "2", "M6", 'W')
            _fill("M8", "1", "M5", 'L'); _fill("M8", "2", "M6", 'L')
            _fill("M11", "1", "M9", 'W'); _fill("M11", "2", "M10", 'W')
            _fill("M12", "1", "M9", 'L'); _fill("M12", "2", "M10", 'L')

        # Zapis z użyciem UTF-8-SIG (żeby Excel poprawnie czytał polskie znaki)
        df.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
        _msc_cup_reload(sex)
        messagebox.showinfo("MSC", f"Faza {phase_key} zaktualizowana pomyślnie.")
        
    def _msc_update_any_from_results(sex: str, which: str):
        """
        sex: 'M' lub 'W'
        which: '1', '2', '3', '1/4', '1/2', 'Finał'
        """
        which = str(which or "").strip()

        # GRUPY (Kolejki 1, 2, 3)
        if which in ("1", "2", "3"):
            # Wywołujemy nową funkcję aktualizującą WSZYSTKIE grupy naraz
            _msc_update_all_groups_from_results(sex, which)
            return

        # FAZY PUCHAROWE (bez zmian)
        phase_map = {"1/4": "QF", "1/2": "SF", "Finał": "F"}
        phase = phase_map.get(which)
        if phase:
            _msc_update_knockout(sex, phase)

    def _cc_final_reload():
            """
            Klasyfikacja końcowa CC:
            - miejsca 1–16 z drabinki pucharowej S45_CC_Puchar.csv
            (Finał + mecze o X miejsce),
            - miejsca 17+ z kwalifikacji Q (S45_Q_CC_M/W/X)
            według sumy punktów z Q.

            Dodatkowo liczymy:
            - "Punkty" = duże punkty z grup (Punkty Zdobyte) + z pucharu (Punkty1/2)
            - Finanse (miejsce) / Finanse (punkty) / Ranking FIS.
            """
            from tkinter import messagebox
            from pathlib import Path
            import pandas as _pd
            import re as _re

            dir_str = cc_dir_var.get()
            dir_path = Path(dir_str.strip() or ".")
            if not dir_path.is_dir():
                messagebox.showerror("CC – klasyfikacja końcowa", f"Folder CC nie istnieje:\n{dir_path}")
                return

            problems = []

            # --- 1) Wczytanie i zsumowanie punktów z Q_CC_M/W/X ---
            data_q = {}  # (Drużyna,Kraj) -> dict(MEN/WOMEN/MIX)

            def _load_q_one(suffix: str, col_name: str):
                nonlocal problems
                # Szukaj najpierw dokładnej nazwy, potem przez glob (*_Q_CC_M*.csv)
                fname = f"S45_Q_CC_{suffix}.csv"
                p = dir_path / fname
                if not p.exists():
                    # fallback: glob po wzorcu (obsługuje np. S45_Q_CC_M_wyniki.csv)
                    candidates = sorted(dir_path.glob(f"*_Q_CC_{suffix}*.csv"))
                    if candidates:
                        p = candidates[0]
                    else:
                        problems.append(f"Brak pliku: {dir_path / fname}")
                        return

                df = None
                last_err = None
                for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
                    try:
                        df = _pd.read_csv(p, sep=None, engine="python", encoding=enc)
                        break
                    except Exception as e:
                        last_err = e
                        df = None
                if df is None:
                    try:
                        df = _pd.read_csv(p, sep=";", encoding="utf-8-sig")
                    except Exception:
                        problems.append(f"Nie mogę wczytać: {p}\n{last_err}")
                        return

                ren = {}
                for c in df.columns:
                    lc = str(c).strip().lower()
                    if lc in {"lp", "lp."}:
                        ren[c] = "Lp."
                    elif "drużyna" in lc or "druzyna" in lc:
                        ren[c] = "Drużyna"
                    elif lc in {"kraj", "nat"}:
                        ren[c] = "Kraj"
                    elif lc.startswith("punkty") or lc.startswith("pkt") or lc == "suma":
                        ren[c] = "Punkty"
                if ren:
                    df = df.rename(columns=ren)

                # fallback: jesli nadal brak Punkty, bierz pierwsza kolumne liczbowa
                if "Punkty" not in df.columns:
                    for _c in df.columns:
                        if _c not in ("Druzyna", "Drużyna", "Kraj", "Lp."):
                            _test = _pd.to_numeric(
                                df[_c].astype(str).str.replace(r"[^\d.\-]", "", regex=True),
                                errors="coerce"
                            )
                            if _test.notna().sum() > 0:
                                df = df.rename(columns={_c: "Punkty"})
                                break

                for col in ("Drużyna", "Kraj", "Punkty"):
                    if col not in df.columns:
                        problems.append(f"Plik {p} nie ma kolumny '{col}'")
                        return

                for _, r in df.iterrows():
                    team = str(r.get("Drużyna", "") or "").strip()
                    nat  = str(r.get("Kraj", "") or "").strip()
                    if not team and not nat:
                        continue
                    key = (team, nat)
                    if key not in data_q:
                        data_q[key] = {"Drużyna": team, "Kraj": nat, "MEN": 0.0, "WOMEN": 0.0, "MIX": 0.0}
                    _raw = str(r.get("Punkty", 0.0) or "0").strip()
                    import re as _re3; _raw = _re3.sub(r"[^\d.\-]", "", _raw)
                    pts = _pd.to_numeric(_raw, errors="coerce")
                    if _pd.isna(pts):
                        pts = 0.0
                    data_q[key][col_name] += float(pts)

            _load_q_one("M", "MEN")
            _load_q_one("W", "WOMEN")
            _load_q_one("X", "MIX")

            rows_q = []
            for (team, nat), vals in data_q.items():
                men = float(vals.get("MEN", 0.0))
                wom = float(vals.get("WOMEN", 0.0))
                mix = float(vals.get("MIX", 0.0))
                suma = men + wom + mix
                rows_q.append(
                    {
                        "Drużyna": team,
                        "Kraj": nat,
                        "MEN": men,
                        "WOMEN": wom,
                        "MIX": mix,
                        "Suma": suma,
                    }
                )

            if not rows_q:
                messagebox.showwarning(
                    "CC – klasyfikacja końcowa",
                    "Brak danych z Q CC (S45_Q_CC_M/W/X)."
                )
                return

            df_q = _pd.DataFrame(rows_q)
            df_q["Drużyna"] = df_q["Drużyna"].astype(str).str.strip()
            df_q["Kraj"] = df_q["Kraj"].astype(str).str.strip().str.upper()
            df_q["Suma"] = _pd.to_numeric(df_q["Suma"], errors="coerce").fillna(0.0)

            # sortowanie jak w Q: po Suma malejąco
            df_q = df_q.sort_values(by=["Suma", "Drużyna"], ascending=[False, True]).reset_index(drop=True)

            # mapa: (Drużyna,Kraj) -> Suma (potrzebna później przy łączeniu z pucharem)
            suma_by_pair = {
                (r["Drużyna"], r["Kraj"]): float(r["Suma"])
                for _, r in df_q.iterrows()
            }

            # --- 1b) Duże punkty z GRUP i PUCHARU ---
            big_pts = {}  # (Drużyna,Kraj) -> liczba dużych punktów

            def _add_big(team: str, nat: str, val) -> None:
                team = (team or "").strip()
                nat = (nat or "").strip().upper()
                if not team or not nat:
                    return
                try:
                    v = float(val)
                except Exception:
                    v = 0.0
                if v == 0.0:
                    return
                key = (team, nat)
                big_pts[key] = big_pts.get(key, 0.0) + v

            # punkty z grup
            for g in ("A", "B", "C", "D"):
                p_g = dir_path / f"S45_CC_Grupa_{g}.csv"
                if not p_g.is_file():
                    continue
                try:
                    df_g = _cc_read_q_csv_any(p_g)
                except Exception as e:
                    problems.append(f"Błąd wczytywania grupy {g}: {e}")
                    continue

                if "Drużyna" not in df_g.columns or "Kraj" not in df_g.columns:
                    continue
                if "Punkty Zdobyte" not in df_g.columns:
                    continue

                df_g["Drużyna"] = df_g["Drużyna"].astype(str).str.strip()
                df_g["Kraj"] = df_g["Kraj"].astype(str).str.strip().str.upper()
                df_g["Punkty Zdobyte"] = _pd.to_numeric(df_g["Punkty Zdobyte"], errors="coerce").fillna(0.0)

                for _, r in df_g.iterrows():
                    _add_big(r["Drużyna"], r["Kraj"], r["Punkty Zdobyte"])

            # --- 2) Wczytanie pucharu i wyciągnięcie miejsc 1–16 z drabinki ---
            p_cup = dir_path / "S45_CC_Puchar.csv"
            if not p_cup.is_file():
                messagebox.showwarning(
                    "CC – klasyfikacja końcowa",
                    f"Brak pliku pucharu:\n{p_cup}\n\nNajpierw ułóż i zapisz drabinkę."
                )
                return

            try:
                df_cup = _cc_read_q_csv_any(p_cup)
            except Exception as e:
                messagebox.showerror("CC – klasyfikacja końcowa", f"Błąd wczytywania pucharu:\n{e}")
                return

            needed_cols = [
                "Mecz", "Faza",
                "Drużyna1", "Kraj1", "Punkty1", "Minipunkty1",
                "Drużyna2", "Kraj2", "Punkty2", "Minipunkty2",
            ]
            for col in needed_cols:
                if col not in df_cup.columns:
                    df_cup[col] = 0 if col.startswith(("Punkty", "Minipunkty")) else ""

            for col in ("Punkty1", "Punkty2", "Minipunkty1", "Minipunkty2"):
                df_cup[col] = _pd.to_numeric(df_cup[col], errors="coerce").fillna(0.0)

            df_cup["Kraj1"] = df_cup["Kraj1"].astype(str).str.strip().str.upper()
            df_cup["Kraj2"] = df_cup["Kraj2"].astype(str).str.strip().str.upper()

            # duże punkty z pucharu
            for _, row in df_cup.iterrows():
                _add_big(row.get("Drużyna1", ""), row.get("Kraj1", ""), row.get("Punkty1", 0.0))
                _add_big(row.get("Drużyna2", ""), row.get("Kraj2", ""), row.get("Punkty2", 0.0))

            final_places: dict[str, int] = {}
            final_team_name: dict[str, str] = {}

            def _set_place(nat: str, team: str, place: int):
                nat = (nat or "").strip().upper()
                if not nat or place is None:
                    return
                if nat not in final_places or place < final_places[nat]:
                    final_places[nat] = int(place)
                    if team:
                        final_team_name[nat] = team

            match_place_map = {
                7: 1,
                8: 3,
                11: 5,
                12: 7,
                15: 9,
                16: 11,
                19: 13,
                20: 15,
            }

            for _, row in df_cup.iterrows():
                try:
                    mecz_raw = str(row.get("Mecz", "") or "").strip()
                    m = _re.search(r"\d+", mecz_raw)
                    mecz_nr = int(m.group(0)) if m else None
                except Exception:
                    mecz_nr = None

                if mecz_nr not in match_place_map:
                    continue

                nat1 = str(row.get("Kraj1", "") or "").strip().upper()
                nat2 = str(row.get("Kraj2", "") or "").strip().upper()
                if not nat1 or not nat2:
                    continue

                p1 = float(row.get("Punkty1", 0.0))
                p2 = float(row.get("Punkty2", 0.0))
                mp1 = float(row.get("Minipunkty1", 0.0))
                mp2 = float(row.get("Minipunkty2", 0.0))

                place_base = match_place_map.get(mecz_nr)

                if place_base is None:
                    faza_raw = str(row.get("Faza", "") or "")
                    faza = faza_raw.lower()
                    if faza.strip() in {"finał", "final"}:
                        if p1 > p2 or (p1 == p2 and mp1 > mp2):
                            _set_place(nat1, str(row.get("Drużyna1", "") or "").strip(), 1)
                            _set_place(nat2, str(row.get("Drużyna2", "") or "").strip(), 2)
                        elif p2 > p1 or (p2 == p1 and mp2 > mp1):
                            _set_place(nat2, str(row.get("Drużyna2", "") or "").strip(), 1)
                            _set_place(nat1, str(row.get("Drużyna1", "") or "").strip(), 2)
                        continue
                    m2 = _re.search(r"(\d+)\s*-\s*(\d+)", faza)
                    if m2:
                        try:
                            low = int(m2.group(1))
                            high = int(m2.group(2))
                            if low % 2 == 1 and high == low + 1 and high <= 16:
                                place_base = low
                            elif low == 1 and high == 4:
                                place_base = 1
                        except Exception:
                            place_base = None

                if place_base is None:
                    continue

                if p1 > p2 or (p1 == p2 and mp1 > mp2):
                    win_nat, win_team = nat1, str(row.get("Drużyna1", "") or "").strip()
                    lose_nat, lose_team = nat2, str(row.get("Drużyna2", "") or "").strip()
                elif p2 > p1 or (p2 == p1 and mp2 > mp1):
                    win_nat, win_team = nat2, str(row.get("Drużyna2", "") or "").strip()
                    lose_nat, lose_team = nat1, str(row.get("Drużyna1", "") or "").strip()
                else:
                    continue

                _set_place(win_nat, win_team, place_base)
                _set_place(lose_nat, lose_team, place_base + 1)

            # --- TOP16 z pucharu ---
            cup_rows = []
            for nat, place in final_places.items():
                if place > 16:
                    continue
                team = final_team_name.get(nat, "")
                if not team:
                    m = df_q[df_q["Kraj"] == nat]
                    if not m.empty:
                        team = str(m.iloc[0]["Drużyna"])
                suma = suma_by_pair.get((team, nat), 0.0)
                cup_rows.append(
                    {
                        "Lp.": int(place),
                        "Drużyna": team,
                        "Kraj": nat,
                        "Suma": float(suma),
                    }
                )

            if not cup_rows:
                messagebox.showwarning(
                    "CC – klasyfikacja końcowa",
                    "Brak rozstrzygniętych meczów o konkretne miejsca w pucharze CC."
                )
                return

            df_cup_final = _pd.DataFrame(cup_rows)
            df_cup_final = df_cup_final.sort_values("Lp.").reset_index(drop=True)

            used_pairs = {(r["Drużyna"], r["Kraj"]) for r in cup_rows}

            # --- ogony 17+ z Q ---
            mask_unused = ~df_q[["Drużyna", "Kraj"]].apply(tuple, axis=1).isin(used_pairs)
            df_tail = df_q[mask_unused].copy().reset_index(drop=True)

            tail_rows = []
            place = 17
            for _, r in df_tail.iterrows():
                tail_rows.append(
                    {
                        "Lp.": place,
                        "Drużyna": r["Drużyna"],
                        "Kraj": r["Kraj"],
                        "Suma": float(r["Suma"]),
                    }
                )
                place += 1

            df_final = _pd.concat([df_cup_final, _pd.DataFrame(tail_rows)], ignore_index=True)
            df_final = df_final.sort_values("Lp.").reset_index(drop=True)

            # --- duże punkty + finanse / ranking ---
            def _get_big_pts(team: str, nat: str) -> float:
                key = ((team or "").strip(), (nat or "").strip().upper())
                return float(big_pts.get(key, 0.0))

            df_final["Punkty"] = [
                _get_big_pts(r.get("Drużyna", ""), r.get("Kraj", ""))
                for _, r in df_final.iterrows()
            ]

            prize_by_place = {
                1: 600_000,
                2: 500_000,
                3: 400_000,
                4: 300_000,
                5: 250_000,
                6: 200_000,
                7: 150_000,
                8: 125_000,
                9: 100_000,
                10: 80_000,
                11: 60_000,
                12: 50_000,
                13: 40_000,
                14: 35_000,
                15: 30_000,
                16: 25_000,
            }

            ranking_fis_by_place = {
                1: 500,
                2: 400,
                3: 300,
                4: 200,
                5: 100,
                6: 75,
                7: 50,
                8: 25,
                9: 10,
                10: 5,
            }

            def _place_prize(p):
                p = int(p)
                return prize_by_place.get(p, 10_000)

            def _place_ranking(p):
                p = int(p)
                return ranking_fis_by_place.get(p, 0)

            df_final["Finanse (miejsce)"] = df_final["Lp."].apply(_place_prize)
            df_final["Finanse (punkty)"] = (
                _pd.to_numeric(df_final["Punkty"], errors="coerce").fillna(0.0) * 20_000.0
            ).round(0).astype(int)
            df_final["Ranking FIS"] = df_final["Lp."].apply(_place_ranking)
            # Finanse (suma) = miejsce + punkty
            df_final["Finanse (suma)"] = (
                _pd.to_numeric(df_final["Finanse (miejsce)"], errors="coerce").fillna(0.0)
                + _pd.to_numeric(df_final["Finanse (punkty)"], errors="coerce").fillna(0.0)
            ).astype(int)

            # --- GUI: rysowanie na canvasie ---
            try:
                _cc_final_draw(df_final)
            except Exception as e:
                problems.append(f"Błąd odświeżenia tabeli w GUI: {e}")

            # --- zapis do CSV ---
            try:
                out_path = dir_path / "S45_CC_Klasyfikacja.csv"
                df_final.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig")
            except Exception as e:
                problems.append(f"Nie udało się zapisać S45_CC_Klasyfikacja.csv: {e}")



    # --- LOGIKA START ---
    def run_simulation():
        global pd
        import pandas as pd

        rng = None

        try:
            K = int(float(k_value.get()))
            HS = int(float(hs_value.get()))
            meter = float(meter_value.get()) if meter_value.get().strip() else compute_meter_value(K)
            w_mean = float(wind_mean_value.get())
            w_sd = float(wind_sd_value.get())
            gate = int(float(gate_value.get()))
            rand = float(randomness_value.get())
            regress = float(elite_regress_value.get())
        except Exception as e:
            messagebox.showerror("Błąd", f"Nieprawidłowe wartości liczbowe:\\n{e}")
            return

        
        # Przygotowanie rosteru
        try:
            if roster_source.get() == "GUI":
                roster = _roster_from_player_db_and_countries(db_frame, country_frame)
                if roster is None or len(roster) == 0:
                    raise RuntimeError("Baza jest pusta lub nie wybrano krajów.")
            else:
                roster = load_roster_custom(Path(excel), sheet_name.get())
        except Exception as e:
            messagebox.showerror("Błąd", "Nie udało się przygotować rosteru:\n{}".format(e))
            return


        df_r1, df_r2, klasyf, all_rounds = simulate_team_competition_ext(
            roster,
            K=K, HS=HS, meter_value=meter,
            wind_ms_mean=w_mean, wind_ms_sd=w_sd,
            gate_base=gate, gate_points_per_step=float(gate_pts_step.get()),
            p_gate_change=float(p_gate_change.get()), max_gate_delta=int(max_gate_delta.get()),
            rng=rng, randomness=rand, elite_regress=regress,
            wind_phi=float(wind_phi.get()), wind_takeoff_gain=float(wind_takeoff_gain.get()),
            wind_flight_gain=float(wind_flight_gain.get()), judges_rho=float(judges_rho.get()),
            finalists_n=int(finalists_n.get()), num_series=int(num_series.get()),
        )
        if klasyf is None:
            messagebox.showwarning("Brak drużyn", "Żaden kraj nie ma min. 4 zawodników.")
            return

        one_series = (int(num_series.get()) == 1)
        df2_for_build = df_r2 if (df_r2 is not None and not df_r2.empty) else pd.DataFrame(columns=df_r1.columns if hasattr(df_r1, 'columns') else ['Druzyna','Zawodnik','Odległość (m)','Punkty rundy'])

        two_rows = build_two_row_table(roster, df_r1, df2_for_build, klasyf.copy() if isinstance(klasyf, pd.DataFrame) else klasyf)
        globals()["_LAST_TWO_ROWS_DATA"] = two_rows

        # [POPRAWKA] Punkty FIS (TEAM) – LICZ ZAWSZE, a widoczność steruj checkboxem
        _scale = {1:400, 2:350, 3:300, 4:250, 5:200, 6:150, 7:100, 8:50}
        def _fis_for(m):
            try:
                mi = int(str(m).strip())
                return _scale.get(mi, 0)
            except Exception:
                return 0
        # realne FIS zawsze do kolumny technicznej
        two_rows["__FIS_TEAM_REAL"] = two_rows.get("Miejsce", "").map(_fis_for)

        # a kolumnę do wyświetlania w GUI wypełnij tylko, gdy checkbox jest włączony
        # domyślnie liczby
        two_rows["Punkty FIS (TEAM)"] = two_rows["__FIS_TEAM_REAL"].astype(float)

        # jeśli checkbox wyłączony -> nie pokazujemy, więc daj NA zamiast stringa
        if not bool(show_fis_team.get()):
            two_rows["Punkty FIS (TEAM)"] = pd.NA

        _mask_detail = two_rows["Miejsce"].astype(str).str.strip().eq("") | two_rows["Miejsce"].isna()
        two_rows.loc[_mask_detail, "Punkty FIS (TEAM)"] = pd.NA

        # Ułóż kolejność kolumn po prawej zależnie od checkboxa
        if bool(show_fis_team.get()):
            order = ["Kraj","Jumper1","Jumper2","Jumper3","Jumper4","Suma","Punkty FIS (TEAM)"]
        else:
            order = ["Kraj","Jumper1","Jumper2","Jumper3","Jumper4","Suma"]

        # --- display-only: usuń NaN z kolumny FIS żeby Treeview nie pokazywał "nan"
        two_rows_display = two_rows.copy()
        if "Punkty FIS (TEAM)" in two_rows_display.columns:
            two_rows_display["Punkty FIS (TEAM)"] = two_rows_display["Punkty FIS (TEAM)"].where(
                two_rows_display["Punkty FIS (TEAM)"].notna(), ""
            )

        table_class.set_dataframe(two_rows_display, order=order)


        # [NOWE] „Schowanie” lub pokazanie kolumny przez zmianę szerokości
        try:
            if bool(show_fis_team.get()):
                table_class.tvR.column("Punkty FIS (TEAM)", width=130, minwidth=100, stretch=False, anchor=tk.E)
                table_class.tvR.heading("Punkty FIS (TEAM)", text="Punkty FIS (TEAM)")
            else:
                table_class.tvR.column("Punkty FIS (TEAM)", width=1, minwidth=1, stretch=False)
        except Exception:
            pass

        # Uporządkuj: Drużyna = pełna nazwa, Kraj = kod (np. SUI → Szwajcaria)

        try:
            if hasattr(two_rows, "columns") and ("Drużyna" in list(two_rows.columns)):
                two_rows = add_team_columns(two_rows, "Drużyna")
        except Exception as _e:
            # nie przerywaj symulacji w razie różnic kolumn
            pass

        falls_df = _build_falls_sheet_compat(df_r1, df2_for_build)

        # Przygotuj ramki do zapisu/podglądu
        dfr1_show = df_r1.rename(columns={'Druzyna':'Kraj'})
        dfr1_show['Drużyna'] = first_series(dfr1_show['Kraj']).map(lambda x: TEAM_NAME.get(str(x), str(x)))

        dfr2_show = pd.DataFrame()
        if df_r2 is not None and not df_r2.empty:
            dfr2_show = df_r2.rename(columns={'Druzyna':'Kraj'})
            dfr2_show['Drużyna'] = first_series(dfr2_show['Kraj']).map(lambda x: TEAM_NAME.get(str(x), str(x)))

        # Bezpiecznie obsłuż brak upadków
        if falls_df is None or getattr(falls_df, 'empty', True):
            falls_df = pd.DataFrame(columns=['Seria','Kraj','Drużyna','Zawodnik','Odległość (m)','Punkty rundy'])
        else:
            # mamy upadki z TEAM – popraw kolumny kraj/drużyna
            falls_df = falls_df.rename(columns={'Druzyna': 'Kraj'})

            # Kraj potrafi być DataFrame, wyciągamy pierwszą kolumnę
            kraj_obj = falls_df["Kraj"]
            kraj_ser = first_series(kraj_obj)
            if kraj_ser is None:
                kraj_ser = kraj_obj

            falls_df["Kraj"] = kraj_ser.astype(str).str.strip()

            # wywal duplikaty nagłówków (w tym wielokrotne "Kraj")
            falls_df = falls_df.loc[:, ~falls_df.columns.duplicated()]

            # nazwa drużyny z mapy TEAM_NAME
            falls_df["Drużyna"] = falls_df["Kraj"].map(lambda x: TEAM_NAME.get(str(x), str(x)))

        # --- Kontuzje po upadkach (TEAM) – użyj silnika z IND GUI, jeśli jest ---
        try:
            if callable(_annotate_falls_with_injuries) and not getattr(falls_df, "empty", True):
                falls_df = _annotate_falls_with_injuries(falls_df, roster, rng or np.random.default_rng())
        except Exception as _inj_e:
            # nie zabijaj konkursu jak kontuzje zawiodą
            print(f"[WARN][TEAM] Kontuzje: {_inj_e}")

        # dorób kolumnę "Płeć" jak w IND GUI, jeśli jest tylko "Sex"
        if "Sex" in falls_df.columns and "Płeć" not in falls_df.columns:
            falls_df["Płeć"] = falls_df["Sex"]

        # --- zapamiętaj ostatnie upadki i agregat, żeby dało się zaktualizować bazę ---
        try:
            self._falls_last_df = falls_df.copy()
        except Exception:
            try:
                self._falls_last_df = falls_df
            except Exception:
                pass

        try:
            import pandas as _pd
            _agg_cols = [c for c in [
                "Zawodnik", "Kraj",
                "Kontuzja (dni)",
                "ΔUM (kontuzja)",
                "ΔForma (kontuzja)",
            ] if c in falls_df.columns]
            if len(_agg_cols) >= 3:
                _ff = falls_df[_agg_cols].copy()
                # --- FIX: wymuś, że Zawodnik i Kraj są 1-wymiarowymi stringami ---
                for col in ("Zawodnik", "Kraj"):
                    if col in _ff.columns:
                        _ff[col] = (
                            _ff[col]
                            .astype(str)
                            .str.replace(r"[\[\]\{\}]", "", regex=True)
                            .str.split("'").str[-1]   # wyciąga czysty tekst z brzydkich struktur
                            .str.strip()
                        )
                _agg = _ff.groupby(["Zawodnik", "Kraj"], as_index=False).agg({
                    "Kontuzja (dni)": "max",
                    "ΔUM (kontuzja)": "min",
                    "ΔForma (kontuzja)": "min",
                })
                self._falls_last_agg = _agg
        except Exception as _agg_e:
            print(f"[WARN][TEAM] Agregat kontuzji: {_agg_e}")
            self._falls_last_agg = None


        if one_series:
            two_rows = drop_fully_empty_rows(two_rows, list(two_rows.columns))
            falls_df = drop_fully_empty_rows(falls_df, list(falls_df.columns))

        two_rows_to_save = two_rows.copy()
        two_rows_to_save.drop(columns=["__FIS_TEAM_REAL"], errors="ignore", inplace=True)

        # zapis — używamy wersji bez kolumny technicznej
        file_path = save_to_excel_custom(
            dfr1_show, dfr2_show, klasyf, two_rows_to_save, falls_df,
            hill_name.get(), outdir.get(), name_pattern.get(),
            one_series=one_series
        )
        tl._last_saved_path = file_path

        if only_save.get():
            msg = f"Wyniki zapisane do: {file_path}"
            if auto_open.get():
                try:
                    os.startfile(str(file_path))
                except Exception:
                    pass
                msg += "\\n(otworzono w Excelu)"
            messagebox.showinfo("Zapisano", msg)
            return

        # ===== PODGLĄD GUI =====
        # --- Klasyfikacja 2-wierszowa: zamrożone "Miejsce" + flaga przy "Drużyna"
        try:
            table_class.clear()
        except Exception:
            clear_table(table_class)  # fallback gdyby stara wersja gdzieś się ostała

        dfc = two_rows.copy()

        # --- do aktualizacji krajów zapisujemy WYŁĄCZNIE klasyfikację drużyn ---
        kl = klasyf.copy()
        # ujednolić nazwy kolumn pod updater
        kl.rename(columns={"Druzyna": "Kraj"}, inplace=True, errors="ignore")

        # jeśli nie ma Punkty FIS w klasyf, to weź z miejsca
        if "Punkty FIS" not in kl.columns and "Miejsce" in kl.columns:
            fis_scale_team = [400, 350, 300, 250, 200, 150, 100, 50]
            m = pd.to_numeric(kl["Miejsce"], errors="coerce").fillna(0).astype(int)
            kl["Punkty FIS"] = m.map(
                lambda x: fis_scale_team[x-1] if 1 <= x <= len(fis_scale_team) else 0
            )

        # --- wyznacz 'Punkty' jako punkty z konkursu ---
        # priorytet:
        #   1) 'Suma'        – suma punktów drużyny
        #   2) 'Punkty drużyny'
        #   3) 'Punkty FIS'  – na wszelki wypadek
        if "Punkty" not in kl.columns:
            if "Suma" in kl.columns:
                kl["Punkty"] = kl["Suma"]
            elif "Punkty drużyny" in kl.columns:
                kl["Punkty"] = kl["Punkty drużyny"]
            elif "Punkty FIS" in kl.columns:
                kl["Punkty"] = kl["Punkty FIS"]
            else:
                kl["Punkty"] = 0

        # Jeśli 'Punkty' istnieją, ale sumarycznie są 0,
        # spróbuj przeliczyć je z 'Punkty1' / 'Punkty2' (typowa sytuacja 1-serii)
        if "Punkty" in kl.columns:
            try:
                pts = pd.to_numeric(kl["Punkty"], errors="coerce").fillna(0)
            except Exception:
                pts = None

            if pts is not None and float(pts.sum() or 0.0) == 0.0:
                p1 = pd.to_numeric(kl["Punkty1"], errors="coerce").fillna(0) if "Punkty1" in kl.columns else None
                p2 = pd.to_numeric(kl["Punkty2"], errors="coerce").fillna(0) if "Punkty2" in kl.columns else None

                if p1 is not None or p2 is not None:
                    s = (p1 if p1 is not None else 0) + (p2 if p2 is not None else 0)
                    kl["Punkty"] = s

        try:
            kl["Punkty"] = pd.to_numeric(kl["Punkty"], errors="coerce").round(1).fillna(0)
        except Exception:
            pass

        global _LAST_TEAM_CLASSIF
        kl["Drużyna"] = kl["Kraj"].map(lambda x: TEAM_NAME.get(str(x), str(x)))
        _LAST_TEAM_CLASSIF = kl.copy()

        # ujednolicenie kolumn punktów w podglądzie (żeby ładnie się wyświetlało)
        if "Suma" not in dfc.columns and "Punkty drużyny" in dfc.columns:
            dfc["Suma"] = dfc["Punkty drużyny"]
        if "Suma" in dfc.columns:
            import pandas as pd
            dfc["Suma"] = pd.to_numeric(dfc["Suma"], errors="coerce").round(1).fillna("")

        # porządek kolumn do wyświetlenia (uwzględnij FIS, jeśli jest i checkbox włączony)
        order = ["Miejsce","Drużyna","Kraj","Jumper1","Jumper2","Jumper3","Jumper4","Suma"]
        if bool(show_fis_team.get()) and "Punkty FIS (TEAM)" in dfc.columns:
            order.append("Punkty FIS (TEAM)")

        table_class.set_dataframe(dfc, order=order)

        # pokaż/schowaj kolumnę przez szerokość
        try:
            if "Punkty FIS (TEAM)" in dfc.columns and bool(show_fis_team.get()):
                table_class.tvR.column("Punkty FIS (TEAM)", width=130, minwidth=100, stretch=False, anchor=tk.E)
                table_class.tvR.heading("Punkty FIS (TEAM)", text="Punkty FIS (TEAM)")
            elif "Punkty FIS (TEAM)" in dfc.columns:
                table_class.tvR.column("Punkty FIS (TEAM)", width=1, minwidth=1, stretch=False)
        except Exception:
            pass

        try:
            table_class.autosize()
            _center_cols_except_team(table_class.tvR, team_col="Drużyna")
        except Exception:
            pass


        # --- przygotuj dane do GUI z flagami ---
        # Upadki: wolimy "Seria" zamiast "Runda", wolimy tekstową "Odległość"
        dff = falls_df.copy()

        # nazwy kolumn jak w IND GUI
        if "Runda" in dff.columns and "Seria" not in dff.columns:
            dff.rename(columns={"Runda": "Seria"}, inplace=True)
        if "Odległość" not in dff.columns and "Odległość (m)" in dff.columns:
            dff.rename(columns={"Odległość (m)": "Odległość"}, inplace=True)

        # Infrastruktura -> Infrastr. (kolumna do wyświetlania)
        if "Infrastruktura" in dff.columns and "Infrastr." not in dff.columns:
            dff["Infrastr."] = dff["Infrastruktura"]

        # Sex = to samo co Płeć (dla spójności z IND)
        if "Płeć" in dff.columns:
            dff["Sex"] = dff.get("Sex", dff["Płeć"])

        # jeśli jest Sex a nie ma Płeć, dorób jak wyżej
        if "Sex" in dff.columns and "Płeć" not in dff.columns:
            dff["Płeć"] = dff["Sex"]

        # Seria 1 i 2: alias Punkty = Punkty rundy, Odległość = Odległość (m) jeśli trzeba
        dfr1v = dfr1_show.copy()
        if "Punkty" not in dfr1v.columns and "Punkty rundy" in dfr1v.columns:
            dfr1v["Punkty"] = dfr1v["Punkty rundy"]
        if "Odległość" not in dfr1v.columns and "Odległość (m)" in dfr1v.columns:
            dfr1v["Odległość"] = dfr1v["Odległość (m)"]

        dfr2v = dfr2_show.copy()
        if dfr2v is not None and not dfr2v.empty:
            if "Punkty" not in dfr2v.columns and "Punkty rundy" in dfr2v.columns:
                dfr2v["Punkty"] = dfr2v["Punkty rundy"]
            if "Odległość" not in dfr2v.columns and "Odległość (m)" in dfr2v.columns:
                dfr2v["Odległość"] = dfr2v["Odległość (m)"]

        # --- wypełnij tabele z flagami ---
        populate_player_rows_with_flags(
            tv_falls, dff,
            name_col="Zawodnik", kraj_col="Kraj",
            cols_out=(
                "Kraj",
                "Seria",
                "Płeć",
                "Lekarz",
                "Infrastr.",
                "Odległość",
                "Kontuzja (rodzaj)",
                "Kontuzja (dni)",
                "Długość kontuzji (WEEK)",
                "Sex",
                "ΔUM (kontuzja)",
                "ΔForma (kontuzja)",
            ),
        )

        populate_player_rows_with_flags(
            tv_r1, dfr1v,
            name_col="Zawodnik", kraj_col="Kraj",
            cols_out=("Kraj","Odległość","Punkty")
        )

        if dfr2v is not None and not dfr2v.empty:
            populate_player_rows_with_flags(
                tv_r2, dfr2v,
                name_col="Zawodnik", kraj_col="Kraj",
                cols_out=("Kraj","Odległość","Punkty")
            )
        else:
            # wyczyść jeśli nie ma drugiej serii
            for iid in tv_r2.get_children(""):
                tv_r2.delete(iid)
            try: tv_r2.img_refs.clear()
            except Exception: pass

        notebook_main.select(tab_results)

        messagebox.showinfo(
        "Sukces",
        f"Zapisano do: {getattr(tl, '_last_saved_path', '')}\nPodgląd w zakładce 'Wyniki'."
    )




# mainloop disabled in embedded mode

    return parent

# ===========================================================
#  FROZEN TABLE HELPER (zintegrowany z team_competition_gui)
# ===========================================================
import tkinter as tk
from tkinter import ttk

class FrozenTable:
    """Tabela z zamrożoną kolumną i płynnym przewijaniem."""
    def __init__(self, parent, *,
                 left_key: str,
                 left_title: str = None,
                 left_width: int = 70,
                 tree_text_key: str = None,
                 tree_title: str = " ",
                 right_cols: list[tuple] = None,
                 image_from_row=None,
                 height: int = 26):

        self.parent = parent
        self.left_key = left_key
        self.tree_text_key = tree_text_key
        self.image_from_row = image_from_row

        wrap = ttk.Frame(parent)
        self.frame = wrap

        vsb = ttk.Scrollbar(wrap, orient="vertical")
        hsb = ttk.Scrollbar(wrap, orient="horizontal")

        tvL = ttk.Treeview(
            wrap, show="headings", height=height,
            yscrollcommand=vsb.set, selectmode="none", takefocus=0
        )
        tvR = ttk.Treeview(
            wrap, show="tree headings", height=height,
            yscrollcommand=vsb.set, xscrollcommand=hsb.set, selectmode="browse"
        )

        # Layout
        tvL.grid(row=0, column=0, sticky="nsew")
        tvR.grid(row=0, column=1, sticky="nsew")
        vsb.grid(row=0, column=2, sticky="ns")
        hsb.grid(row=1, column=1, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=0)
        wrap.columnconfigure(1, weight=1)

        # Kolumny
        tvL["columns"] = (left_key,)
        tvL.heading(left_key, text=left_title or left_key)
        tvL.column(left_key, width=left_width, minwidth=left_width, anchor=tk.CENTER)

        tvR["columns"] = tuple(c[0] for c in (right_cols or []))
        tvR.heading("#0", text=tree_title)
        tvR.column("#0", width=220, minwidth=160, anchor=tk.W)
        for name, width, align in (right_cols or []):
            anc = {"e": tk.E, "center": tk.CENTER}.get(align, tk.W)
            tvR.heading(name, text=name)
            tvR.column(name, width=width, minwidth=min(width, 100), anchor=anc, stretch=False)

        # --- płynny scroll ---
        _syncing_y = {"flag": False}
        def _ysync_from(other, bar):
            def _cb(lo, hi):
                bar.set(lo, hi)
                if _syncing_y["flag"]:
                    return
                try:
                    _syncing_y["flag"] = True
                    other.yview_moveto(float(lo))
                finally:
                    _syncing_y["flag"] = False
            return _cb

        tvL.configure(yscrollcommand=_ysync_from(tvR, vsb))
        tvR.configure(yscrollcommand=_ysync_from(tvL, vsb))
        def _on_scrollbar_y(*args):
            if args and args[0] == "moveto":
                frac = float(args[1])
                tvL.yview_moveto(frac)
                tvR.yview_moveto(frac)
            else:
                n, what = int(args[1]), args[2]
                tvL.yview_scroll(n, what)
                tvR.yview_scroll(n, what)
        vsb.config(command=_on_scrollbar_y)
        hsb.config(command=tvR.xview)

        # kółko myszy
        def _on_mousewheel(evt):
            if getattr(evt, "num", None) == 4:
                n = -1
            elif getattr(evt, "num", None) == 5:
                n = 1
            else:
                n = -int(evt.delta / 120) if getattr(evt, "delta", 0) else 0
            if n:
                tvR.yview_scroll(n, "units")
            return "break"
        for w in (tvL, tvR):
            w.bind("<Enter>", lambda e, ww=w: ww.focus_set())
            w.bind("<MouseWheel>", _on_mousewheel)
            w.bind("<Button-4>", _on_mousewheel)
            w.bind("<Button-5>", _on_mousewheel)

        # --- highlight po lewej ---
        _current_hl = {"iid": None}
        try:
            tvL.tag_configure("_HL", background="#dce8ff")
        except Exception:
            tvL.tag_configure("_HL", background="#dce8ff")

        def _clear_hl():
            iid = _current_hl["iid"]
            if iid and tvL.exists(iid):
                tvL.item(iid, tags=tuple(t for t in tvL.item(iid, "tags") if t != "_HL"))
            _current_hl["iid"] = None

        def _apply_hl(iid):
            _clear_hl()
            if iid and tvL.exists(iid):
                tags = list(tvL.item(iid, "tags"))
                if "_HL" not in tags:
                    tags.append("_HL")
                tvL.item(iid, tags=tuple(tags))
                _current_hl["iid"] = iid

        def _on_right_select(event=None):
            sel = tvR.selection()
            iid = sel[0] if sel else ""
            if iid:
                tvL.see(iid)
            _apply_hl(iid)
        tvR.bind("<<TreeviewSelect>>", _on_right_select, add="+")

        def _on_left_click_select(event):
            iid = tvL.identify_row(event.y)
            if not iid:
                tvR.selection_remove(tvR.selection())
                _clear_hl()
                return "break"
            if tvR.exists(iid):
                tvR.selection_set(iid)
                tvR.focus(iid)
                tvR.see(iid)
                _apply_hl(iid)
                return "break"
        tvL.bind("<Button-1>", _on_left_click_select, add="+")

        # zapamiętaj
        self.tvL, self.tvR = tvL, tvR

    # public API
    def widget(self):
        return self.frame
    def clear(self):
        for tv in (self.tvL, self.tvR):
            for iid in tv.get_children(""):
                tv.delete(iid)

    def insert_row(self, row: dict):
        import pandas as pd
        
        # 1. Zapewnienie listy referencji na obrazki (aby flagi nie znikały)
        if not hasattr(self, "img_refs"):
            self.img_refs = []

        # 2. Wstawienie wiersza do lewej (zamrożonej) części
        iid = self.tvL.insert(
            "",
            "end",
            values=(row.get(self.left_key, ""),)
        )

        # 3. Przygotowanie tekstu i obrazka (flagi)
        txt = f" {row.get(self.tree_text_key, '')}"
        img = self.image_from_row(row) if self.image_from_row else None
        
        if img:
            self.img_refs.append(img) # Zapamiętanie referencji

        # 4. PRZYGOTOWANIE WARTOŚCI (Naprawa błędu NameError: vals)
        vals = [] # Definicja zmiennej przed pętlą
        for c in self.tvR["columns"]:
            v = row.get(c, "")
            # Obsługa wartości NaN z pandas
            try:
                if pd.isna(v): v = ""
            except Exception:
                pass
            vals.append(str(v))

        # 5. Wstawienie danych do prawej części tabeli
        self.tvR.insert(
            "", 
            "end", 
            iid=iid, 
            text=txt, 
            image=(img or ""), 
            values=tuple(vals) # Teraz 'vals' jest już poprawnie zdefiniowane
        )

    def set_dataframe(self, df, order=None):
        import pandas as pd
        self.clear()
        dfx = df.copy()
        if order:
            dfx = dfx[[c for c in order if c in dfx.columns]]
        for _, r in dfx.iterrows():
            self.insert_row(dict(r))
    def autosize(self):
        self.tvL.column(self.left_key, width=max(60, self.tvL.column(self.left_key, "width")))

def create_frozen_table(parent, **kwargs):
    ft = FrozenTable(parent, **kwargs)
    return ft.widget(), ft

# ============================
#  KONIEC FROZEN TABLE HELPER
# ============================

def _center_cols_except_team(tv: ttk.Treeview, team_col: str = "Drużyna"):
    """
    Ustawia wyśrodkowanie dla wszystkich kolumn w Treeview poza kolumną 'Drużyna',
    którą zostawia wyrównaną do lewej. Dba też o nagłówki.
    """
    try:
        cols = list(tv["columns"])
    except Exception:
        return
    # #0 (jeśli używany) zostaw po lewej, żeby nazwy nie wyglądały jak cegła
    try:
        tv.column("#0", anchor="w")
        tv.heading("#0", anchor="w")
    except Exception:
        pass

    for c in cols:
        anch = "w" if c == team_col else "center"
        try:
            tv.column(c, anchor=anch)
        except Exception:
            pass
        try:
            tv.heading(c, anchor=anch)
        except Exception:
            pass

# === Standalone launcher ===
if __name__ == "__main__":
    try:
        import tkinter as tk
        from tkinter import messagebox
        _root = tk.Tk()
        _root.title("Team Competition GUI (embedded)")
        try:
            build_gui(_root)
        except Exception as e:
            # surface any init error
            messagebox.showerror("Błąd inicjalizacji", str(e))
            raise
        _root.mainloop()
    except Exception as e:
        # Fallback print + pause in console to prevent auto-close
        import sys, traceback
        traceback.print_exc()
        try:
            input("Wciśnij Enter, aby zamknąć...")
        except Exception:
            pass
# === End standalone launcher ===