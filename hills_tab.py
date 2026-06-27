# -*- coding: utf-8 -*-
"""
hills_tab.py — Moduł z dwiema podzakładkami:
 - "Skocznie"        → CSV: Skocznie S51.csv (Treeview + flagi)
 - "Infrastruktura"  → CSV: Infrastruktura S51.csv (CanvasGrid z kolorowaniem komórek)

Użycie:
    from pathlib import Path
    from hills_tab import HillsTab
    self.hills_tab = HillsTab(
        parent,
        default_hills=Path("Skocznie S51.csv"),
        default_infra=Path("Infrastruktura S51.csv"),
        flags_dir=Path("./flags"),
    )
    self.hills_tab.pack(fill="both", expand=True)
"""
from __future__ import annotations

from pathlib import Path
import math
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import pandas as pd
import unicodedata, re as _re

__all__ = ["HillsTab"]

FLAG_COL_CANDIDATES = ["Reprezentacja", "Kraj", "NAT", "Nation"]
_FLAG_IMG_CACHE = {}

HOMOLOGATION_SPEC = {
    "OLYMPIC CLASS": {
        "Miejsca dla kibiców": "15000",
        "Oświetlenie": "1000",
        "Igielit": "-",
        "Tablica wyników": "elektr.",
        "Kabina komentatorska": "poz 5",
        "Kabina sędziowska": "+",
        "Poczekalnia dla zawodników": "wyborny",
        "Siatka wiatrochłonna": "+",
        "Naśnieżanie": "B",
    },
    "WORLD CUP CLASS": {
        "Miejsca dla kibiców": "10000",
        "Oświetlenie": "500",
        "Igielit": "-",
        "Tablica wyników": "elektr.",
        "Kabina komentatorska": "poz 4",
        "Kabina sędziowska": "+",
        "Poczekalnia dla zawodników": "dobry",
        "Siatka wiatrochłonna": "+",
        "Naśnieżanie": "A",
    },
    "CONTINENTAL CUP CLASS": {
        "Miejsca dla kibiców": "2500",
        "Oświetlenie": "-",
        "Igielit": "-",
        "Tablica wyników": "zwykła",
        "Kabina komentatorska": "-",
        "Kabina sędziowska": "+",
        "Poczekalnia dla zawodników": "średni",
        "Siatka wiatrochłonna": "-",
        "Naśnieżanie": "-",
    },
    "JUNIOR CUP CLASS": {
        "Miejsca dla kibiców": "-",
        "Oświetlenie": "-",
        "Igielit": "-",
        "Tablica wyników": "zwykła",
        "Kabina komentatorska": "-",
        "Kabina sędziowska": "-",
        "Poczekalnia dla zawodników": "-",
        "Siatka wiatrochłonna": "-",
        "Naśnieżanie": "-",
    },
}

# ── Klasa operacyjna: stałe ──────────────────────────────────────────────────
_OP_CHOICES = ["Pełna", "Połowiczna", "Minimalna"]
_OP_MULTIPLIERS = {"Pełna": 1.0, "Połowiczna": 0.6, "Minimalna": 0.2}

_POC_SCORE = {"wyborny": 4, "dobry": 3, "sredni": 2, "średni": 2, "niski": 1, "-": 0, "": 0}
_TW_SCORE  = {"elektr.": 2, "elektr": 2, "zwykla": 1, "zwykła": 1, "-": 0, "": 0}
_NAS_SCORE = {"b": 2, "a": 1, "-": 0, "": 0}

_TW_DEGRADE  = {"elektr.": "zwykła", "elektr": "zwykła", "zwykła": "-", "zwykla": "-", "-": "-"}
_NAS_DEGRADE = {"b": "A", "a": "-", "-": "-"}
_POC_DEGRADE = {"wyborny": "dobry", "dobry": "średni", "sredni": "niski", "średni": "niski",
                "niski": "-", "-": "-", "": "-"}
_KK_DEGRADE  = {"poz 5": "poz 4", "poz 4": "poz 3", "poz 3": "poz 2",
                "poz 2": "poz 1", "poz 1": "-", "-": "-", "": "-"}

# Kolejność klas FIS (od najwyższej do najniższej)
_FIS_CLASS_ORDER = [
    "OLYMPIC CLASS", "WORLD CUP CLASS", "CONTINENTAL CUP CLASS", "JUNIOR CUP CLASS"
]

# Mapowanie pól HOMOLOGATION_SPEC → kolumny CSV skoczni (po normalizacji)
_HOMO_FIELD_COL = {
    "Miejsca dla kibiców": "Miejsca dla kibiców",
    "Oświetlenie":          "OŚ",
    "Tablica wyników":      "Tw",
    "Kabina komentatorska": "Kk",
    "Kabina sędziowska":    "Ks",
    "Poczekalnia dla zawodników": "Poc",
    "Siatka wiatrochłonna": "Sia",
    "Naśnieżanie":          "Naś",
}


def _homo_check_row(row, klass: str) -> list:
    """Zwraca listę niespełnionych wymagań dla klasy. Pusta lista = spełnione."""
    spec = HOMOLOGATION_SPEC.get(klass, {})
    failures = []

    def _v(col):
        return str(row.get(col) or "").strip()

    for field, req in spec.items():
        if req == "-":
            continue
        col = _HOMO_FIELD_COL.get(field, field)
        val = _v(col)

        if field in ("Miejsca dla kibiców", "Oświetlenie"):
            if _to_int_safe(val) < _to_int_safe(req):
                failures.append(f"{field}: {val or '–'} (wym. {req})")
        elif field == "Tablica wyników":
            if _TW_SCORE.get(_norm_str(val), 0) < _TW_SCORE.get(_norm_str(req), 0):
                failures.append(f"{field}: {val or '–'} (wym. {req})")
        elif field == "Kabina komentatorska":
            def _kk_num(s):
                m = _re.search(r"(\d+)", s)
                return int(m.group(1)) if m else 0
            if _kk_num(val) < _kk_num(req):
                failures.append(f"{field}: {val or '–'} (wym. {req})")
        elif field in ("Kabina sędziowska", "Siatka wiatrochłonna"):
            if val != "+":
                failures.append(f"{field}: {val or '–'} (wym. +)")
        elif field == "Poczekalnia dla zawodników":
            if _POC_SCORE.get(_norm_str(val), 0) < _POC_SCORE.get(_norm_str(req), 0):
                failures.append(f"{field}: {val or '–'} (wym. {req})")
        elif field == "Naśnieżanie":
            if _NAS_SCORE.get(val.lower(), 0) < _NAS_SCORE.get(req.lower(), 0):
                failures.append(f"{field}: {val or '–'} (wym. {req})")

    return failures


def _homo_best_class(row) -> str:
    """Zwraca najwyższą klasę FIS jaką spełnia wiersz skoczni."""
    for klass in _FIS_CLASS_ORDER:
        if not _homo_check_row(row, klass):
            return klass
    return "Brak klasy"


def _effective_fis_class(actual: str, op_class: str) -> str:
    """Zwraca efektywną klasę FIS po uwzględnieniu klasy operacyjnej."""
    actual_up = actual.strip().upper()
    idx = next((i for i, c in enumerate(_FIS_CLASS_ORDER) if c in actual_up), None)
    if op_class == "Pełna" or idx is None:
        return actual
    if op_class == "Połowiczna":
        new_idx = idx + 1
        return _FIS_CLASS_ORDER[new_idx] if new_idx < len(_FIS_CLASS_ORDER) else "-"
    if op_class == "Minimalna":
        if idx >= len(_FIS_CLASS_ORDER) - 1:
            return "-"
        return _FIS_CLASS_ORDER[-1]
    return actual


def _compute_current_fis_class(row) -> str:
    """Oblicza najwyższą klasę FIS jaką kompleks aktualnie spełnia."""
    def _v(col):
        return str(row.get(col) or "-").strip()

    seats = _to_int_safe(_v("Miejsca dla kibicow"))
    os_v  = _to_int_safe(_v("OS"))
    tw    = _norm_str(_v("Tw"))
    poc   = _norm_str(_v("Poc"))
    nas   = _norm_str(_v("Nas"))
    kk    = _v("Kk")
    ks    = _v("Ks")
    sia   = _v("Sia")

    poc_s = _POC_SCORE.get(poc, 0)
    tw_s  = _TW_SCORE.get(tw, 0)
    nas_s = _NAS_SCORE.get(nas, 0)

    def kk_num():
        m = re.search(r"(\d+)", kk)
        return int(m.group(1)) if m else 0

    checks = [
        ("OLYMPIC CLASS",       seats >= 15000 and os_v >= 1000 and tw_s >= 2 and kk_num() >= 5
                                and ks == "+" and poc_s >= 4 and sia == "+" and nas_s >= 2),
        ("WORLD CUP CLASS",     seats >= 10000 and os_v >= 500  and tw_s >= 2 and kk_num() >= 4
                                and ks == "+" and poc_s >= 3 and sia == "+" and nas_s >= 1),
        ("CONTINENTAL CUP CLASS", seats >= 2500 and tw_s >= 1 and ks == "+" and poc_s >= 2),
        ("JUNIOR CUP CLASS",    tw_s >= 1),
    ]
    for name, ok in checks:
        if ok:
            return name
    return "Brak klasy"


def load_operational_classes(path) -> pd.DataFrame:
    """Wczytuje Klasa operacyjna S51.csv lub zwraca pusty DataFrame."""
    p = Path(path)
    if p.exists():
        for enc in ("utf-8", "utf-8-sig", "cp1250"):
            try:
                df = pd.read_csv(p, sep=";", dtype=str, encoding=enc)
                df.columns = [c.strip() for c in df.columns]
                return df
            except Exception:
                pass
    return pd.DataFrame(columns=["Kraj", "Miasto", "Klasa", "Sezony_POL", "Sezony_MIN"])


def save_operational_classes(df: pd.DataFrame, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, sep=";", index=False, encoding="utf-8")


def apply_operational_multipliers(df_rows: pd.DataFrame, df_op: pd.DataFrame) -> pd.DataFrame:
    """
    Stosuje mnożniki klasy operacyjnej do df_rows (per kompleks),
    agreguje wynik po Kraju i zwraca DataFrame z kolumnami [Kraj, Suma].
    """
    if df_rows is None or df_rows.empty:
        return pd.DataFrame(columns=["Kraj", "Suma"])

    op_lookup: dict = {}
    if df_op is not None and not df_op.empty:
        for _, r in df_op.iterrows():
            k = (str(r.get("Kraj", "")).strip().upper(), str(r.get("Miasto", "")).strip())
            op_lookup[k] = str(r.get("Klasa", "Pełna")).strip()

    out = df_rows.copy()
    out["_mult"] = out.apply(
        lambda r: _OP_MULTIPLIERS.get(
            op_lookup.get((str(r.get("Kraj","")).strip().upper(), str(r.get("Miasto","")).strip()), "Pełna"),
            1.0
        ), axis=1
    )
    out["Suma_eff"] = (pd.to_numeric(out["Suma"], errors="coerce").fillna(0) * out["_mult"]).round(0).astype(int)

    by_country = out.groupby("Kraj", dropna=False)["Suma_eff"].sum().reset_index()
    by_country.rename(columns={"Suma_eff": "Suma"}, inplace=True)
    return by_country


def apply_season_end_degradation(df_op: pd.DataFrame, hills_path) -> tuple:
    """
    Przetwarza koniec sezonu:
      • Połowiczna → Sezony_POL += 1, Sezony_MIN = 0
      • Minimalna  → Sezony_MIN += 1, Sezony_POL = 0
      • Pełna      → oba liczniki = 0
      • Sezony_POL >= 3  → degradacja infrastruktury, reset Sezony_POL
      • Sezony_MIN >= 2  → degradacja infrastruktury, reset Sezony_MIN
    Degradowane: Tw, Naś, Poc, Kk (o 1 poziom), OS (-500), Ks→-, Sia→-
    Zwraca (df_op_updated, lista komunikatów o degradacjach).
    """
    df = df_op.copy()
    for col, default in (("Sezony_POL", 0), ("Sezony_MIN", 0)):
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    to_degrade = []
    for idx, row in df.iterrows():
        klasa = str(row.get("Klasa", "Pełna")).strip()
        sp = int(row.get("Sezony_POL", 0))
        sm = int(row.get("Sezony_MIN", 0))

        if klasa == "Połowiczna":
            sp, sm = sp + 1, 0
        elif klasa == "Minimalna":
            sp, sm = 0, sm + 1
        else:
            sp, sm = 0, 0

        df.at[idx, "Sezony_POL"] = sp
        df.at[idx, "Sezony_MIN"] = sm

        kraj  = str(row.get("Kraj",   "")).strip().upper()
        miasto = str(row.get("Miasto", "")).strip()
        if sp >= 3:
            to_degrade.append((kraj, miasto))
            df.at[idx, "Sezony_POL"] = 0
        elif sm >= 2:
            to_degrade.append((kraj, miasto))
            df.at[idx, "Sezony_MIN"] = 0

    messages = []
    hp = Path(hills_path) if hills_path else None
    if to_degrade and hp and hp.exists():
        df_hills = None
        for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
            try:
                df_hills = pd.read_csv(hp, sep=";", dtype=str, encoding=enc)
                break
            except Exception:
                pass

        if df_hills is not None:
            def _find(name):
                return next((c for c in df_hills.columns if _norm_str(c) == name), None)

            tw_col  = _find("tw")
            nas_col = _find("nas")
            poc_col = _find("poc")
            kk_col  = _find("kk")
            os_col  = _find("os")
            ks_col  = _find("ks")
            sia_col = _find("sia")
            kraj_col   = _find("kraj")
            miasto_col = _find("miasto")

            changed = False
            for kraj, miasto in to_degrade:
                if kraj_col is None or miasto_col is None:
                    continue
                mask = (
                    df_hills[kraj_col].astype(str).str.strip().str.upper().eq(kraj) &
                    df_hills[miasto_col].astype(str).str.strip().eq(miasto)
                )
                if not mask.any():
                    continue
                parts = []
                for ridx in df_hills[mask].index:
                    if tw_col:
                        old = _norm_str(df_hills.at[ridx, tw_col])
                        new = _TW_DEGRADE.get(old)
                        if new and new != old:
                            parts.append(f"Tw: {old}→{new}")
                            df_hills.at[ridx, tw_col] = new
                            changed = True
                    if nas_col:
                        old = _norm_str(df_hills.at[ridx, nas_col])
                        new = _NAS_DEGRADE.get(old)
                        if new and new != old.upper() and new != old:
                            parts.append(f"Naś: {old.upper()}→{new}")
                            df_hills.at[ridx, nas_col] = new
                            changed = True
                    if poc_col:
                        old = _norm_str(df_hills.at[ridx, poc_col])
                        new = _POC_DEGRADE.get(old)
                        if new and new != old:
                            parts.append(f"Poc: {old}→{new}")
                            df_hills.at[ridx, poc_col] = new
                            changed = True
                    if kk_col:
                        old = str(df_hills.at[ridx, kk_col]).strip().lower()
                        new = _KK_DEGRADE.get(old)
                        if new and new != old:
                            parts.append(f"Kk: {old}→{new}")
                            df_hills.at[ridx, kk_col] = new
                            changed = True
                    if os_col:
                        raw = str(df_hills.at[ridx, os_col]).strip()
                        try:
                            val = int(float(raw))
                            new_val = max(0, val - 500)
                            new_str = str(new_val) if new_val > 0 else "-"
                            if new_str != raw:
                                parts.append(f"OS: {raw}→{new_str}")
                                df_hills.at[ridx, os_col] = new_str
                                changed = True
                        except ValueError:
                            pass
                    if ks_col:
                        old = str(df_hills.at[ridx, ks_col]).strip()
                        if old not in ("-", ""):
                            parts.append(f"Ks: {old}→-")
                            df_hills.at[ridx, ks_col] = "-"
                            changed = True
                    if sia_col:
                        old = str(df_hills.at[ridx, sia_col]).strip()
                        if old not in ("-", ""):
                            parts.append(f"Sia: {old}→-")
                            df_hills.at[ridx, sia_col] = "-"
                            changed = True
                if parts:
                    messages.append(f"{kraj} / {miasto}: {', '.join(parts)}")

            if changed:
                df_hills.to_csv(hp, sep=";", index=False, encoding="utf-8")

    return df, messages


def _load_nations_for_cycle(search_dir: Path, prev_s: str, cycle: str, suf: str) -> list:
    """Wczytuje listę NAT z pliku klasyfikacji w kolejności rankingowej."""
    names = [
        f"{prev_s}_{cycle}-{suf}__nations.csv",
        f"{prev_s}_{cycle}_{suf}__nations.csv",
        f"{cycle}-{suf}__nations.csv",
        f"{cycle}_{suf}__nations.csv",
    ]
    for name in names:
        p = Path(search_dir) / name
        if p.exists():
            for enc in ("utf-8-sig", "utf-8", "cp1250"):
                try:
                    df = pd.read_csv(p, sep=None, engine="python", encoding=enc)
                    df.columns = [str(c).strip().upper() for c in df.columns]
                    c_nat = next((c for c in ("NAT", "KRAJ", "NATION") if c in df.columns), None)
                    if c_nat:
                        return df[c_nat].dropna().map(lambda x: str(x).strip()).unique().tolist()
                except Exception:
                    pass
    return []


def _compute_slot_lim(rank: int, cycle: str, gender: str) -> int:
    """Zwraca liczbę slotów eventów dla danego miejsca i cyklu (ta sama logika co w SeasonPlannerFrame)."""
    if cycle == "WC":
        if gender == "M":
            if rank == 1: return 5
            if rank <= 5: return 4
            if rank <= 14: return 2
        else:
            if rank <= 4: return 4
            if rank == 5: return 3
            if rank <= 14: return 2
        return 0
    if cycle == "COC":
        top = 3 if gender == "M" else 2
        if rank <= top: return 4
        if rank <= 15: return 2
        return 0
    if cycle == "FC":
        cutoff = 15 if gender == "M" else 14
        return 2 if rank <= cutoff else 0
    # JC, MC, PC, QC, TC, AC, BC, DC
    return 2 if rank <= 5 else 0


def _build_interleaved_ranking(m_list: list, w_list: list) -> list:
    """Splata ranking M i W naprzemiennie (jak w GP/SCOC), usuwa duplikaty."""
    combined = []
    for m, w in zip(m_list, w_list):
        combined.extend([m, w])
    longer = m_list if len(m_list) > len(w_list) else w_list
    combined.extend(longer[min(len(m_list), len(w_list)):])
    seen: set = set()
    return [x for x in combined if not (x in seen or seen.add(x))]


def compute_op_class_demands(search_dir, prev_s: str) -> tuple:
    """
    Oblicza zapotrzebowanie na skocznie per kraj z klasyfikacji poprzedniego sezonu.
    Zwraca (country_demand, wc_demand):
      country_demand: {NAT: suma floor(lim/2)} bez bonusu juniorskiego
      wc_demand:      {NAT: demand tylko z WC-M + WC-W}
    """
    country_demand: dict = {}
    wc_demand: dict = {}

    def _add(nat: str, d: int, to_wc: bool = False):
        if d <= 0:
            return
        nat = nat.strip().upper()
        country_demand[nat] = country_demand.get(nat, 0) + d
        if to_wc:
            wc_demand[nat] = wc_demand.get(nat, 0) + d

    # WC, COC, FC – osobno M i W
    for cycle in ("WC", "COC", "FC"):
        for suf in ("M", "W"):
            for i, nat in enumerate(_load_nations_for_cycle(search_dir, prev_s, cycle, suf)):
                lim = _compute_slot_lim(i + 1, cycle, suf)
                _add(nat, lim // 2, to_wc=(cycle == "WC"))

    # GP – interleaved M+W, top 5 dostaje lim=2 → demand=1
    gp = _build_interleaved_ranking(
        _load_nations_for_cycle(search_dir, prev_s, "GP", "M"),
        _load_nations_for_cycle(search_dir, prev_s, "GP", "W"),
    )
    for i, nat in enumerate(gp):
        if i < 5: _add(nat, 1)

    # SCOC – interleaved M+W, top 3 dostaje lim=2 → demand=1
    scoc = _build_interleaved_ranking(
        _load_nations_for_cycle(search_dir, prev_s, "SCOC", "M"),
        _load_nations_for_cycle(search_dir, prev_s, "SCOC", "W"),
    )
    for i, nat in enumerate(scoc):
        if i < 3: _add(nat, 1)

    # Juniorskie (JC, MC, PC, QC, TC, AC, BC, DC) – osobno M i W, top 5 → demand=1
    for cycle in ("JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"):
        for suf in ("M", "W"):
            for i, nat in enumerate(_load_nations_for_cycle(search_dir, prev_s, cycle, suf)):
                if i < 5: _add(nat, 1)

    return country_demand, wc_demand


def _get_flag_image(flags_dir: Path | None, code: str):
    """
    Zwraca tk.PhotoImage z cache dla kodu kraju (np. 'AUT').
    Oczekuje plików PNG 18x11 w katalogu flags.
    """
    if not flags_dir or not code:
        return None
    key = str(flags_dir), code.upper()
    if key in _FLAG_IMG_CACHE:
        return _FLAG_IMG_CACHE[key]
    p = flags_dir / f"{code.upper()}.png"
    if not p.exists():
        p = flags_dir / f"{code.lower()}.png"
        if not p.exists():
            return None
    try:
        img = tk.PhotoImage(file=str(p))
        _FLAG_IMG_CACHE[key] = img
        return img
    except Exception:
        return None

# === AGREGACJA KOMPLEKSÓW Z „SKOCZNIE S51.csv” ===

def _kx_from_hs_list(hs_vals):
    """Z listy HS-ów w mieście zbuduj Kx: F (HS>179), L (111-179), N (<111)."""
    has_F = any(pd.to_numeric(hs_vals, errors="coerce").fillna(0) >= 180)
    has_L = any((pd.to_numeric(hs_vals, errors="coerce").fillna(0) >= 111) &
                (pd.to_numeric(hs_vals, errors="coerce").fillna(0) <= 179))
    has_N = any(pd.to_numeric(hs_vals, errors="coerce").fillna(0) <= 110)
    parts = []
    if has_F: parts.append("F")
    if has_L: parts.append("L")
    if has_N: parts.append("N")
    return "".join(parts)

def _canon_hdr(s: str) -> str:
    s = str(s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # usuń ogonki
    s = _re.sub(r"[^a-z0-9]+", "", s)  # tylko a-z0-9 (używamy _re, bo _re2 nie istnieje)
    return s

def _col_val(row, *cands):
    for c in cands:
        if c in row.index:
            return row.get(c)
    return None

def _num(row, *cands) -> int:
    return _to_int_safe(_col_val(row, *cands))

def build_complexes_from_hills(df_hills: pd.DataFrame) -> pd.DataFrame:
    """
    Z DF „Skocznie” zrób DF „Kompleksy”:
      - grupowanie po (Reprezentacja, Kraj, Miasto),
      - Ig = liczba skoczni z igielitem (kolumna 'Ig' == 1 / 'Tak' / '+'),
      - Kx = litery z klas HS (F/L/N),
      - pozostałe pola bierzemy z pierwszego (zakładamy identyczne w mieście).
    """
    if df_hills is None or len(df_hills) == 0:
        return pd.DataFrame(columns=["Reprezentacja","Kraj","Miasto","Miejsca dla kibicow","OS","Ig","Kx","Tw","Kk","Ks","Poc","Sia","Nas"])

    df = df_hills.copy()

    # Ujednolicenia nagłówków minimalne (łagodne – bez rozbijania istniejącej logiki)
    rename = {}
    mapping = {
        "reprezentacja": "Reprezentacja",
        "countryname":   "Reprezentacja",
        "nazwakraju":    "Reprezentacja",

        "kraj": "Kraj", "nat": "Kraj", "code": "Kraj", "iso3": "Kraj", "iso3code": "Kraj",

        "miasto": "Miasto", "city": "Miasto",

        "hs": "HS",

        "igielit": "Ig", "ig": "Ig",

        "miejscadlakibicow": "Miejsca dla kibicow",
        "miejsca": "Miejsca dla kibicow",
        "pojemnosc": "Miejsca dla kibicow",

        "os": "OS", "oswietlenie": "OS", "oswie tlenie": "OS",

        "tw": "Tw",
        "kk": "Kk",
        "ks": "Ks",
        "poc": "Poc",
        "sia": "Sia",

        # tu klucz: „Naś” po kanonizacji też da „nas”
        "nas": "Nas",
    }
    for c in df.columns:
        key = _canon_hdr(c)
        if key in mapping:
            rename[c] = mapping[key]
    if rename:
        df = df.rename(columns=rename)

    # Przytnij do kolumn, których potrzebuje Kompleksy
    needed = ["Reprezentacja","Kraj","Miasto","Miejsca dla kibicow","OS","Ig","HS","Tw","Kk","Ks","Poc","Sia","Nas"]
    for c in needed:
        if c not in df.columns:
            df[c] = pd.NA

    # Normalizacja prostych pól
    df["Kraj"] = df["Kraj"].astype(str).str.upper().str.strip()
    df["Miasto"] = df["Miasto"].astype(str).str.strip()

    # Ig per skocznia → 0/1
    def _ig_bin(x):
        s = str(x).strip().lower()
        return 1 if s in {"1","tak","+","t","yes","y"} else 0
    df["_Ig.bin"] = df["Ig"].map(_ig_bin)

    # Agregacja po mieście
    grp_keys = ["Reprezentacja","Kraj","Miasto"]
    g = df.groupby(grp_keys, dropna=False)

    def _first_nonnull(s):
        try:
            return s.dropna().iloc[0]
        except Exception:
            return s.iloc[0] if len(s) else pd.NA

    out = g.apply(lambda d: pd.Series({
        "Miejsca dla kibicow": _first_nonnull(d["Miejsca dla kibicow"]),
        "OS": _first_nonnull(d["OS"]),
        "Ig": int(d["_Ig.bin"].sum()),         # liczba igielitów w mieście
        "Kx": _kx_from_hs_list(d["HS"]),       # litery F/L/N wg HS z miasta
        "Tw": _first_nonnull(d["Tw"]),
        "Kk": _first_nonnull(d["Kk"]),
        "Ks": _first_nonnull(d["Ks"]),
        "Poc": _first_nonnull(d["Poc"]),
        "Sia": _first_nonnull(d["Sia"]),
        "Nas": _first_nonnull(d["Nas"]),
    }), include_groups=False).reset_index()

    # Upewnij się, że „Miejsca dla kibicow” jest liczbą (stringi z odstępami → int)
    out["Miejsca dla kibicow"] = out["Miejsca dla kibicow"].map(_to_int_safe)

    # Opcjonalnie: ostrzeż, jeśli w mieście pola nie były identyczne (poza Ig/HS)
    # Celowo cicho: zbieramy tylko diagnostykę do konsoli.
    for col in ["Miejsca dla kibicow","OS","Tw","Kk","Ks","Poc","Sia","Nas"]:
        try:
            bad = g[col].nunique(dropna=False) > 1
            if getattr(bad, "any", lambda: False)():
                print(f"[Kompleksy] Ostrzeżenie: w {col} wykryto różne wartości w tym samym mieście.")
        except Exception:
            pass

    # Kolejność jak w dotychczasowych Kompleksach
    return out[["Reprezentacja","Kraj","Miasto","Miejsca dla kibicow","OS","Ig","Kx","Tw","Kk","Ks","Poc","Sia","Nas"]]


def _to_int_safe(x):
    # "36 100" -> 36100, "–" / "-" / None -> 0
    if x is None:
        return 0

    # jeśli to już liczba (int/float) – bierz po prostu część całkowitą
    if isinstance(x, (int, float)):
        try:
            return int(x)
        except Exception:
            pass

    s = str(x).strip().replace("\u00a0", " ")
    if s in {"-", "–", ""}:
        return 0

    import re
    s = re.sub(r"[^\d]", "", s)
    return int(s) if s else 0

def _norm_str(x):
    import unicodedata
    s = str(x).strip().lower() if x is not None else ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def _seats_cost_eur_bucketed(n: int) -> int:
    """
    Jednolita stawka za CAŁĄ pojemnOSć wg progu:
      0–10 000  -> 2 €/miejsce
      10 001–20 000 -> 3 €/miejsce
      20 001–30 000 -> 5 €/miejsce
      30 001–50 000 -> 8 €/miejsce
      50 001–75 000 -> 12 €/miejsce
      75 001+       -> 20 €/miejsce
    """
    try:
        n = int(n)
    except Exception:
        n = 0
    if n <= 0:
        return 0

    if n <= 10_000:
        rate = 2
    elif n <= 20_000:
        rate = 3
    elif n <= 30_000:
        rate = 5
    elif n <= 50_000:
        rate = 8
    elif n <= 75_000:
        rate = 12
    else:
        rate = 20
    return n * rate

def _parse_kx(val):
    # FLN=200k, FL=100k, FN=75k, LN=50k, wszystko inne=0
    v = _norm_str(val)
    return {
        "fln": 200_000,
        "fl": 100_000,
        "fn": 75_000,
        "ln": 50_000,
    }.get(v, 0)

def _parse_tw(val):
    # zwykła=5k, elektr.=12k
    v = _norm_str(val)
    if v.startswith("elektr"):
        return 12_000
    if v in {"zwykla", "zwykła", "zwykla.", "zwykła."}:
        return 5_000
    # gdy wpisano cOS dziwnego, ale nie puste, przyjmij „zwykła”
    return 5_000 if v not in {"", "-"} else 0

def _parse_poz(val):
    # "poz 1..5" -> mapowanie kwot
    v = _norm_str(val)
    m = re.search(r"(\d+)", v)
    lvl = int(m.group(1)) if m else 0
    return {1: 5_000, 2: 10_000, 3: 20_000, 4: 30_000, 5: 40_000}.get(lvl, 0)

def _parse_plus(val):
    # '+' -> 5000, reszta 0
    return 5_000 if _norm_str(val) == "+" else 0

def _parse_poc(val):
    v = _norm_str(val)
    return {
        "niski": 5_000,
        "sredni": 10_000,
        "średni": 10_000,
        "dobry": 20_000,
        "wyborny": 30_000,
    }.get(v, 0)

def _parse_nas(val):
    v = _norm_str(val)
    return {"a": 5_000, "b": 15_000}.get(v, 0)

def compute_complex_costs(df):
    """
    Przyjmuje DF z 'Kompleksy S51.csv' i zwraca:
      - df_rows: koszty dla każdego obiektu,
      - by_country_sum: suma per kraj,
      - by_country_breakdown: rozbicie per składnik per kraj,
      - by_country_with_count: suma + liczba obiektów,
      - ranking: suma malejąco + udział %.
    """
    # Nazwy kolumn wg Twojego nagłówka:
    # Reprezentacja, Kraj, Miasto, Miejsca dla kibicow, OS, Ig, Kx, Tw, Kk, Ks, Poc, Sia, Nas

    seats = df["Miejsca dla kibicow"].map(_to_int_safe) if "Miejsca dla kibicow" in df else 0
    osw   = df["OS"].map(_to_int_safe) if "OS" in df else 0
    ig    = df["Ig"].map(_to_int_safe) if "Ig" in df else 0

    kx = df["Kx"].map(_parse_kx) if "Kx" in df else 0
    tw = df["Tw"].map(_parse_tw) if "Tw" in df else 0
    kk = df["Kk"].map(_parse_poz) if "Kk" in df else 0
    ks = df["Ks"].map(_parse_plus) if "Ks" in df else 0
    poc = df["Poc"].map(_parse_poc) if "Poc" in df else 0
    sia = df["Sia"].map(_parse_plus) if "Sia" in df else 0
    nas = df["Nas"].map(_parse_nas) if "Nas" in df else 0

    # Wzory:
    # Miejsca: 2 € za każde miejsce
    cost_seats = seats.map(_seats_cost_eur_bucketed)
    # OS: 5000 € za każde 500 (w CSV i tak będzie wielokrotnOSć 500)
    cost_osw = (osw // 500) * 5_000
    # IG: 5000 € za każdy 1
    cost_ig = ig * 5_000

    # Suma per obiekt
    total = cost_seats + cost_osw + cost_ig + kx + tw + kk + ks + poc + sia + nas

    df_rows = pd.DataFrame({
        "Reprezentacja": df.get("Reprezentacja", pd.Series([""] * len(df))),
        "Kraj": df.get("Kraj", pd.Series([""] * len(df))),
        "Miasto": df.get("Miasto", pd.Series([""] * len(df))),
        "cost_seats": cost_seats,
        "cost_osw": cost_osw,
        "cost_ig": cost_ig,
        "cost_kx": kx,
        "cost_tw": tw,
        "cost_kk": kk,
        "cost_ks": ks,
        "cost_poc": poc,
        "cost_sia": sia,
        "cost_nas": nas,
        "Suma": total,
    })

    # Agregacje per kraj
    by = "Kraj"
    agg_cols = ["cost_seats","cost_osw","cost_ig","cost_kx","cost_tw","cost_kk","cost_ks","cost_poc","cost_sia","cost_nas","Suma"]

    by_country_breakdown = df_rows.groupby(by, dropna=False)[agg_cols].sum().reset_index()
    by_country_breakdown[agg_cols] = (
        by_country_breakdown[agg_cols]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
    )
    by_country_sum = by_country_breakdown[["Kraj","Suma"]].copy()
    by_country_sum["Suma"] = pd.to_numeric(by_country_sum["Suma"], errors="coerce").fillna(0)

    by_country_with_count = by_country_breakdown.copy()
    by_country_with_count["Liczba obiektów"] = df_rows.groupby(by, dropna=False).size().reindex(by_country_with_count["Kraj"]).values
    by_country_with_count = by_country_with_count[["Kraj","Liczba obiektów","Suma"] + [c for c in agg_cols if c not in {"Suma"}]]

    ranking = by_country_sum.sort_values("Suma", ascending=False).reset_index(drop=True)
    ranking["Suma"] = pd.to_numeric(ranking["Suma"], errors="coerce").fillna(0)

    total_all = float(ranking["Suma"].sum()) or 1.0
    ranking["Udział %"] = (ranking["Suma"] / total_all * 100).round(2)

    return df_rows, by_country_sum, by_country_breakdown, by_country_with_count, ranking

def _fmt_eur(df, cols, with_symbol=True):
    out = df.copy()
    for c in cols:
        if c in out:
            # 1) liczby → numeric
            ser = pd.to_numeric(out[c], errors="coerce").fillna(0)

            # 2) zaokrąglenie i int
            ser = ser.round(0).astype("int64")

            # 3) formatowanie bez dodawania stringa do serii (zero operatora +)
            def _fmt_one(v: int) -> str:
                s = f"{v:,}".replace(",", " ").replace("\u00a0", " ")
                return f"{s} €" if with_symbol else s

            out[c] = pd.Series((_fmt_one(int(v)) for v in ser.tolist()), index=out.index, dtype="object")
    return out

def _build_k_cost(val) -> int:
    """Cennik punktu K przy budowie nowej skoczni."""
    k = _to_int_safe(val)
    table = {
        65: 125_000,
        70: 150_000,
        75: 175_000,
        80: 200_000,
        85: 225_000,
        90: 250_000,
        95: 275_000,
        100: 300_000,
        105: 400_000,
        110: 450_000,
        115: 475_000,
        120: 500_000,
        125: 525_000,
        130: 550_000,
        135: 575_000,
        140: 600_000,
        165: 650_000,
        170: 700_000,
        175: 750_000,
        180: 800_000,
        185: 850_000,
        190: 900_000,
        195: 950_000,
        200: 1_000_000,
        205: 1_050_000,
        210: 1_100_000,
        215: 1_150_000,
        220: 1_200_000,
        225: 1_250_000,
    }
    return int(table.get(k, 0))

# --- bazowy koszt z pojedynczego "snapshota" (budowa) ---
def _snapshot_base_cost(row) -> int:
    k = _num(row, "K", "k")
    hs = _num(row, "HS", "Hs", "hs")
    seats = _num(row, "Miejsca dla kibiców", "Miejsca dla kibicow")
    osw = _num(row, "OŚ", "Os", "OS")

    ig = str(_col_val(row, "Ig", "IG", "ig") or "").strip()
    tw = _norm_str(_col_val(row, "Tw", "TW") or "")
    kk = _norm_str(_col_val(row, "Kk", "KK") or "")
    ks = str(_col_val(row, "Ks", "KS") or "").strip()
    poc = _norm_str(_col_val(row, "Poc", "POC") or "")
    sia = str(_col_val(row, "Sia", "SIA") or "").strip()
    nas = _norm_str(_col_val(row, "Naś", "Nas", "NAS") or "")

    cost = 0

    # Punkt K
    cost += _build_k_cost(k)

    # Miejsca dla kibiców: każde 58
    if seats > 0:
        cost += seats * 58

    # Oświetlenie: każde 500 -> 80 000
    if osw > 0:
        cost += (osw // 500) * 80_000

    # Igielit: HS * 500 (jeżeli '+')
    if ig == "+":
        cost += hs * 500

    # Tablica wyników
    if "elektr" in tw:
        cost += 100_000
    elif "zwyk" in tw:
        cost += 40_000

    # Kabina komentatorska (poz 1-5)
    lvl = 0
    m = re.search(r"(\d+)", kk)
    if m:
        try:
            lvl = int(m.group(1))
        except Exception:
            lvl = 0
    kk_map = {1: 40_000, 2: 70_000, 3: 110_000, 4: 150_000, 5: 200_000}
    cost += kk_map.get(lvl, 0)

    # Kabina sędziowska
    if ks == "+":
        cost += 50_000

    # Poczekalnia
    poc_map = {
        "niski": 25_000,
        "sredni": 75_000,
        "dobry": 125_000,
        "wyborny": 250_000,
    }
    if poc:
        cost += poc_map.get(poc, 0)

    # Siatka
    if "+" in sia:
        cost += 75_000

    # Naśnieżanie
    nas_map = {"a": 100_000, "b": 300_000}
    if nas:
        cost += nas_map.get(nas, 0)

    return int(cost)

# --- dodatkowe koszty / zniżki za typ inwestycji (dla BUDOWA) ---
def _add_investment_extras(row, base_cost: int) -> int:
    raw = str(_col_val(row, "Typ inwestycji") or "")
    items = [s.strip().lower() for s in raw.split(",") if s.strip()]

    # Czy to jedna z trzech: normalna/duża/mamucia w kompleksie?
    has_normal = "nowa skocznia normalna w kompleksie" in items
    has_big1  = "nowa skocznia duża w kompleksie" in items
    has_big2  = "nowa skocznia duza w kompleksie" in items  # bez ogonka na wszelki wypadek
    has_mamm  = "nowa skocznia mamucia w kompleksie" in items

    special_complex = has_normal or has_big1 or has_big2 or has_mamm

    if special_complex:
        # Tylko: koszt K + igielit
        k  = _to_int_safe(_col_val(row, "K"))
        hs = _to_int_safe(_col_val(row, "HS"))
        ig = str(_col_val(row, "Ig") or "").strip()

        cost_k = _build_k_cost(k)
        cost_ig = hs * 500 if ig == "+" and hs > 0 else 0

        cost = int(cost_k + cost_ig)
    else:
        # Standardowo: bierzemy pełny base_cost policzony z całej infrastruktury
        cost = int(base_cost)

    # Teraz dokładamy „koszt inwestycji” zależny od typu
    has_kraj = any("nowa skocznia w kraju" in i for i in items)
    if "nowa skocznia" in items:
        cost += 300_000
    if has_kraj:
        cost += 300_000
    if has_normal:
        cost += 200_000
    if has_big1 or has_big2:
        cost += 500_000
    if has_mamm:
        cost += 1_000_000

    # Zniżka 50% dla "Nowa skocznia w kraju"
    if has_kraj and cost > 0:
        cost = int(round(cost * 0.5))

    return int(cost)

# --- koszt rozbudowy z pary PRZED/PO ---
def _rebuild_cost(row_before, row_after) -> int:
    cost = 0

    # pomocnicze
    def nb(*cs): return _to_int_safe(_col_val(row_before, *cs))
    def na(*cs): return _to_int_safe(_col_val(row_after, *cs))

    import math

    # K – różnica w cenniku (tylko w górę)
    k_b = nb("K", "k")
    k_a = na("K", "k")
    if k_a and k_a != k_b:
        diff = _build_k_cost(k_a) - _build_k_cost(k_b)
        if diff > 0:
            cost += diff

    # HS – do igielitu
    hs_a = na("HS", "Hs", "hs") or nb("HS", "Hs", "hs")

    # Miejsca dla kibiców – tylko różnica w górę
    seats_b = nb("Miejsca dla kibiców", "Miejsca dla kibicow")
    seats_a = na("Miejsca dla kibiców", "Miejsca dla kibicow")
    d_seats = max(0, seats_a - seats_b)
    if d_seats > 0:
        cost += d_seats * 58

    # Oświetlenie – różnica
    os_b = nb("OŚ", "Os", "OS")
    os_a = na("OŚ", "Os", "OS")
    d_os = max(0, os_a - os_b)
    if d_os > 0:
        cost += (d_os // 500) * 80_000

    # Igielit – wchodzi z '-' na '+'
    ig_b = str(_col_val(row_before, "Ig", "IG", "ig") or "").strip()
    ig_a = str(_col_val(row_after, "Ig", "IG", "ig") or "").strip()
    if ig_b != "+" and ig_a == "+":
        cost += hs_a * 500

    # Tablica wyników – pełna cena targetu
    tw_b = _norm_str(_col_val(row_before, "Tw", "TW") or "")
    tw_a = _norm_str(_col_val(row_after, "Tw", "TW") or "")
    if tw_a and tw_a != tw_b:
        if "elektr" in tw_a:
            cost += 100_000
        elif "zwyk" in tw_a:
            cost += 40_000

    # Kabina komentatorska – pełna cena targetu
    kk_b = _norm_str(_col_val(row_before, "Kk", "KK") or "")
    kk_a = _norm_str(_col_val(row_after, "Kk", "KK") or "")
    if kk_a and kk_a != kk_b:
        kk_map = {1: 40_000, 2: 70_000, 3: 110_000, 4: 150_000, 5: 200_000}
        m = re.search(r"(\d+)", kk_a)
        lvl_a = int(m.group(1)) if m else 0
        cost += kk_map.get(lvl_a, 0)

    # Kabina sędziowska – tylko wejście z '-' na '+'
    ks_b = str(_col_val(row_before, "Ks", "KS") or "").strip()
    ks_a = str(_col_val(row_after, "Ks", "KS") or "").strip()
    if ks_b != "+" and ks_a == "+":
        cost += 50_000

    # Poczekalnia – pełna cena docelowego poziomu
    poc_b = _norm_str(_col_val(row_before, "Poc", "POC") or "")
    poc_a = _norm_str(_col_val(row_after, "Poc", "POC") or "")
    poc_map = {
        "niski": 25_000,
        "sredni": 75_000,
        "dobry": 125_000,
        "wyborny": 250_000,
    }
    if poc_a and poc_a != poc_b:
        cost += poc_map.get(poc_a, 0)

    # Siatka – z '-' na '+'
    sia_b = str(_col_val(row_before, "Sia", "SIA") or "")
    sia_a = str(_col_val(row_after, "Sia", "SIA") or "")
    if "+" not in sia_b and "+" in sia_a:
        cost += 75_000

    # Naśnieżanie – pełna cena docelowej klasy
    nas_b = _norm_str(_col_val(row_before, "Naś", "Nas", "NAS") or "")
    nas_a = _norm_str(_col_val(row_after, "Naś", "Nas", "NAS") or "")
    nas_map = {"a": 100_000, "b": 300_000}
    if nas_a and nas_a != nas_b:
        cost += nas_map.get(nas_a, 0)

    return int(cost)

def compute_build_extend_costs(df_log):
    """
    Liczy koszty budowy / rozbudowy na podstawie logu Rozbudowa S51.csv.

    Zwraca:
      - df_invest: wiersz na inwestycję (TS) z kolumnami:
        TS, Tryb, Reprezentacja, Kraj, Miasto, Skocznia, Typ inwestycji, Koszt
      - df_by_country: suma kosztów per kraj (Kraj, Suma)
    """
    import pandas as pd
    import re

    if df_log is None or getattr(df_log, "empty", True):
        empty_inv = pd.DataFrame(columns=[
            "TS", "Tryb", "Reprezentacja", "Kraj", "Miasto", "Skocznia", "Typ inwestycji", "Koszt"
        ])
        empty_sum = pd.DataFrame(columns=["Kraj", "Suma"])
        return empty_inv, empty_sum

    df = df_log.copy()

    # Spróbuj znaleźć kolumny TS i pierwszy 'Stan' (PRZED/PO/BUDOWA)
    col_ts = next((c for c in df.columns if str(c).strip().lower() == "ts"), None)
    col_stan = None
    for c in df.columns:
        if str(c).strip().lower() == "stan":
            col_stan = c
            break

    if col_ts is None or col_stan is None:
        empty_inv = pd.DataFrame(columns=[
            "TS", "Tryb", "Reprezentacja", "Kraj", "Miasto", "Skocznia", "Typ inwestycji", "Koszt"
        ])
        empty_sum = pd.DataFrame(columns=["Kraj", "Suma"])
        return empty_inv, empty_sum

    df[col_stan] = df[col_stan].astype(str).str.strip().str.upper()




    records = []

    # --- BUDOWA (pojedyncze wiersze) ---
    df_build = df[df[col_stan] == "BUDOWA"]
    for _, row in df_build.iterrows():
        base = _snapshot_base_cost(row)
        cost = _add_investment_extras(row, base)
        rec = {
            "TS": row.get(col_ts, ""),
            "Tryb": "Budowa",
            "Reprezentacja": row.get("Reprezentacja", ""),
            "Kraj": row.get("Kraj", ""),
            "Miasto": row.get("Miasto", ""),
            "Skocznia": row.get("Skocznia", ""),
            "Typ inwestycji": row.get("Typ inwestycji", ""),
            "Koszt": int(cost),
        }
        records.append(rec)

    # --- ROZBUDOWA (pary PRZED/PO grupowane po TS + Skocznia + Miasto) ---
    df_reb = df[df[col_stan].isin(["PRZED", "PO"])].copy()
    if not df_reb.empty:
        # Wykryj kolumny Skocznia i Miasto (jeśli istnieją)
        col_skocznia = next((c for c in df_reb.columns if str(c).strip().lower() == "skocznia"), None)
        col_miasto = next((c for c in df_reb.columns if str(c).strip().lower() == "miasto"), None)

        # Zbuduj klucz grupowania: TS + Skocznia + Miasto — by nie mieszać skoczni z tym samym timestampem
        group_key_cols = [col_ts]
        if col_skocznia:
            # fillna("") żeby NaN nie był odrzucany przez groupby
            df_reb["_grp_skocznia"] = df_reb[col_skocznia].fillna("").astype(str).str.strip()
            group_key_cols.append("_grp_skocznia")
        if col_miasto:
            df_reb["_grp_miasto"] = df_reb[col_miasto].fillna("").astype(str).str.strip()
            group_key_cols.append("_grp_miasto")

        for key_vals, grp in df_reb.groupby(group_key_cols, dropna=False):
            ts = key_vals if isinstance(key_vals, str) else key_vals[0]
            g = grp.sort_values(col_stan)
            row_before = g[g[col_stan] == "PRZED"].head(1)
            row_after = g[g[col_stan] == "PO"].tail(1)
            if row_before.empty or row_after.empty:
                continue
            rb = row_before.iloc[0]
            ra = row_after.iloc[0]
            cost = _rebuild_cost(rb, ra)
            rec = {
                "TS": ts,
                "Tryb": "Rozbudowa",
                "Reprezentacja": ra.get("Reprezentacja", ""),
                "Kraj": ra.get("Kraj", ""),
                "Miasto": ra.get("Miasto", ""),
                "Skocznia": ra.get("Skocznia", ""),
                "Typ inwestycji": "Rozbudowa",
                "Koszt": int(cost),
            }
            records.append(rec)

    import pandas as _pd
    df_inv = _pd.DataFrame.from_records(records) if records else _pd.DataFrame(
        columns=["TS", "Tryb", "Reprezentacja", "Kraj", "Miasto", "Skocznia", "Typ inwestycji", "Koszt"]
    )

    if df_inv.empty:
        df_sum = _pd.DataFrame(columns=["Kraj", "Suma"])
    else:
        df_sum = df_inv.groupby("Kraj", as_index=False)["Koszt"].sum()
        df_sum.rename(columns={"Koszt": "Suma"}, inplace=True)

    return df_inv, df_sum

# === Formularz: Budowa / Rozbudowa skoczni ===
class BuildExtendForm(ttk.Frame):
    """
    Prostokątny formularz do wyliczania kosztów i zapisu do CSV 'Kompleksy'.
    Operuje na tych polach: Reprezentacja, Kraj, Miasto, Miejsca dla kibicow, OS, Ig, Kx, Tw, Kk, Ks, Poc, Sia, Nas
    """
    def __init__(self, parent, get_complexes_path_callable, flags_dir: Path | None = None):
        super().__init__(parent)
        self._get_complexes_path = get_complexes_path_callable
        self._flags_dir = flags_dir

        # wartOSci formularza
        self.var_rep = tk.StringVar(value="")
        self.var_nat = tk.StringVar(value="")
        self.var_city = tk.StringVar(value="")
        self.var_seats = tk.IntVar(value=0)     # Miejsca dla kibicow
        self.var_os = tk.IntVar(value=0)        # OS (krotnOSć 500)
        self.var_ig = tk.IntVar(value=0)        # Ig
        self.var_kx = tk.StringVar(value="-")   # FLN/FL/FN/LN/-
        self.var_tw = tk.StringVar(value="Zwykła")  # Zwykła/Elektroniczna/-
        self.var_kk = tk.StringVar(value="-")   # Poz 1..5 lub '-'
        self.var_ks = tk.StringVar(value="-")   # '+' lub '-'
        self.var_poc = tk.StringVar(value="-")  # Niski/Średni/Dobry/Wyborny/-
        self.var_sia = tk.StringVar(value="-")  # '+' lub '-'
        self.var_nas = tk.StringVar(value="-")  # A/B/-

        # nagłówek
        top = ttk.Frame(self); top.pack(fill=tk.X, padx=8, pady=(8,6))
        ttk.Label(top, text="Formularz budowy / rozbudowy skoczni").pack(side=tk.LEFT)

        body = ttk.Frame(self); body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        for c in range(4): body.columnconfigure(c, weight=1)

        r = 0
        ttk.Label(body, text="Reprezentacja (pełna nazwa):").grid(row=r, column=0, sticky="w"); 
        ttk.Entry(body, textvariable=self.var_rep).grid(row=r, column=1, sticky="ew")
        ttk.Label(body, text="Kraj (NAT, np. AUT):").grid(row=r, column=2, sticky="w"); 
        ttk.Entry(body, textvariable=self.var_nat, width=8).grid(row=r, column=3, sticky="w"); r+=1

        ttk.Label(body, text="Miasto:").grid(row=r, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.var_city).grid(row=r, column=1, sticky="ew")
        ttk.Label(body, text="Miejsca dla kibicow:").grid(row=r, column=2, sticky="w")
        ttk.Spinbox(body, from_=0, to=500000, increment=100, textvariable=self.var_seats, width=10)\
            .grid(row=r, column=3, sticky="w"); r+=1

        ttk.Label(body, text="OS (krotnOSć 500):").grid(row=r, column=0, sticky="w")
        ttk.Spinbox(body, from_=0, to=100000, increment=500, textvariable=self.var_os, width=10)\
            .grid(row=r, column=1, sticky="w")
        ttk.Label(body, text="Ig (szt.):").grid(row=r, column=2, sticky="w")
        ttk.Spinbox(body, from_=0, to=1000, increment=1, textvariable=self.var_ig, width=10)\
            .grid(row=r, column=3, sticky="w"); r+=1

        ttk.Label(body, text="Kx (Komplex):").grid(row=r, column=0, sticky="w")
        ttk.Combobox(body, textvariable=self.var_kx, values=["FLN","FL","FN","LN","-"], width=10, state="readonly").grid(row=r, column=1, sticky="w")
        ttk.Label(body, text="Tablica wyników:").grid(row=r, column=2, sticky="w")
        ttk.Combobox(body, textvariable=self.var_tw, values=["Zwykła","Elektroniczna","-"], width=16, state="readonly").grid(row=r, column=3, sticky="w"); r+=1

        ttk.Label(body, text="Kabina kom. (poziom):").grid(row=r, column=0, sticky="w")
        ttk.Combobox(body, textvariable=self.var_kk, values=["-","1","2","3","4","5"], width=10, state="readonly").grid(row=r, column=1, sticky="w")
        ttk.Label(body, text="Konstrukcje stal. (Ks):").grid(row=r, column=2, sticky="w")
        ttk.Combobox(body, textvariable=self.var_ks, values=["-","+"], width=10, state="readonly").grid(row=r, column=3, sticky="w"); r+=1

        ttk.Label(body, text="Położenie (Poc):").grid(row=r, column=0, sticky="w")
        ttk.Combobox(body, textvariable=self.var_poc, values=["-","Niski","Średni","Dobry","Wyborny"], width=12, state="readonly").grid(row=r, column=1, sticky="w")
        ttk.Label(body, text="Siatki (Sia):").grid(row=r, column=2, sticky="w")
        ttk.Combobox(body, textvariable=self.var_sia, values=["-","+"], width=10, state="readonly").grid(row=r, column=3, sticky="w"); r+=1

        ttk.Label(body, text="NagłOSnienie (Nas):").grid(row=r, column=0, sticky="w")
        ttk.Combobox(body, textvariable=self.var_nas, values=["-","A","B"], width=10, state="readonly").grid(row=r, column=1, sticky="w"); r+=1

        # podsumowanie
        sumf = ttk.Labelframe(self, text="Koszty (EUR)"); sumf.pack(fill=tk.X, padx=8, pady=(6,8))
        self.lbl_seats = tk.StringVar(value="0 €")
        self.lbl_os = tk.StringVar(value="0 €")
        self.lbl_ig = tk.StringVar(value="0 €")
        self.lbl_kx = tk.StringVar(value="0 €")
        self.lbl_tw = tk.StringVar(value="0 €")
        self.lbl_kk = tk.StringVar(value="0 €")
        self.lbl_ks = tk.StringVar(value="0 €")
        self.lbl_poc = tk.StringVar(value="0 €")
        self.lbl_sia = tk.StringVar(value="0 €")
        self.lbl_nas = tk.StringVar(value="0 €")
        self.lbl_total = tk.StringVar(value="0 €")

        def row_sum(frm, r, name, var):
            ttk.Label(frm, text=name).grid(row=r, column=0, sticky="w")
            ttk.Label(frm, textvariable=var).grid(row=r, column=1, sticky="w")

        for i in range(2): sumf.columnconfigure(i, weight=1)
        row_sum(sumf, 0, "Miejsca dla kibicow", self.lbl_seats)
        row_sum(sumf, 1, "OS", self.lbl_os)
        row_sum(sumf, 2, "Igielit", self.lbl_ig)
        row_sum(sumf, 3, "Komplex (Kx)", self.lbl_kx)
        row_sum(sumf, 4, "Tablica wyników", self.lbl_tw)
        row_sum(sumf, 5, "Kabina komentatorska (Kk)", self.lbl_kk)
        row_sum(sumf, 6, "Konstrukcje stalowe (Ks)", self.lbl_ks)
        row_sum(sumf, 7, "Położenie (Poc)", self.lbl_poc)
        row_sum(sumf, 8, "Siatki (Sia)", self.lbl_sia)
        row_sum(sumf, 9, "NagłOSnienie (Nas)", self.lbl_nas)
        ttk.Separator(sumf).grid(row=10, column=0, columnspan=2, sticky="ew", pady=4)
        row_sum(sumf, 11, "SUMA", self.lbl_total)

        # przyciski
        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=8, pady=(0,8))
        ttk.Button(bar, text="Przelicz", command=self._recalc).pack(side=tk.LEFT)
        ttk.Button(bar, text="Zapisz do 'Kompleksy' (dodaj/aktualizuj)", command=self._save_row).pack(side=tk.LEFT, padx=8)

        for v in (self.var_seats, self.var_os, self.var_ig, self.var_kx, self.var_tw, self.var_kk, self.var_ks, self.var_poc, self.var_sia, self.var_nas):
            v.trace_add("write", lambda *args: self._recalc())

    def _fmt(self, x):
        try:
            x = int(round(float(x)))
        except Exception:
            x = 0
        return f"{x:,}".replace(",", " ") + " €"

    def _map_kk(self, s):
        s = str(s).strip()
        return {"1": 5_000, "2":10_000, "3":20_000, "4":30_000, "5":40_000}.get(s, 0)

    def _map_plus(self, s):
        return 5_000 if str(s).strip() == "+" else 0

    def _map_tw(self, s):
        w = str(s).strip().lower()
        if w.startswith("elekt"): return 12_000
        if w in {"zwykła", "zwykla", "zwykła.", "zwykla."}: return 5_000
        return 0

    def _map_kx(self, s):
        return {"fln":200_000, "fl":100_000, "fn":75_000, "ln":50_000}.get(str(s).strip().lower(), 0)

    def _map_poc(self, s):
        w = str(s).strip().lower()
        return {"niski":5_000, "średni":10_000, "sredni":10_000, "dobry":20_000, "wyborny":30_000}.get(w, 0)

    def _map_nas(self, s):
        return {"a":5_000, "b":15_000}.get(str(s).strip().lower(), 0)

    def _investment_type_text(self) -> str:
        """
        Zbiera stany checkboxów 'Nowa skocznia ...' i zwraca czytelny opis.
        Jeśli nic nie zaznaczono, zwraca '—' (myślnik).
        """
        # self.build_flags: dict[str, tk.BooleanVar] – już istnieje w formularzu
        # Mapowanie: klucz -> etykieta do CSV
        label = []
        mapping = {
            "nowa": "Nowa skocznia",
            "nowa_normalna": "Nowa skocznia normalna w kompleksie",
            "nowa_duza": "Nowa skocznia duża w kompleksie",
            "nowa_mamucia": "Nowa skocznia mamucia w kompleksie",
            "nowa_kraj": "Nowa skocznia w kraju",
        }
        for key, text in mapping.items():
            try:
                if key in self.build_flags and self.build_flags[key].get():
                    label.append(text)
            except Exception:
                pass
        return ", ".join(label) if label else "—"

    def _recalc(self):
        seats = int(self.var_seats.get() or 0)
        osw = int(self.var_os.get() or 0)
        ig = int(self.var_ig.get() or 0)

        cost_seats = _seats_cost_eur_bucketed(seats)   # ta sama stawka progowa, co w kompleksach :contentReference[oaicite:1]{index=1}
        cost_os = (osw // 500) * 5_000
        cost_ig = ig * 5_000
        cost_kx = self._map_kx(self.var_kx.get())
        cost_tw = self._map_tw(self.var_tw.get())
        cost_kk = self._map_kk(self.var_kk.get())
        cost_ks = self._map_plus(self.var_ks.get())
        cost_poc = self._map_poc(self.var_poc.get())
        cost_sia = self._map_plus(self.var_sia.get())
        cost_nas = self._map_nas(self.var_nas.get())

        total = sum([cost_seats, cost_os, cost_ig, cost_kx, cost_tw, cost_kk, cost_ks, cost_poc, cost_sia, cost_nas])

        self.lbl_seats.set(self._fmt(cost_seats))
        self.lbl_os.set(self._fmt(cost_os))
        self.lbl_ig.set(self._fmt(cost_ig))
        self.lbl_kx.set(self._fmt(cost_kx))
        self.lbl_tw.set(self._fmt(cost_tw))
        self.lbl_kk.set(self._fmt(cost_kk))
        self.lbl_ks.set(self._fmt(cost_ks))
        self.lbl_poc.set(self._fmt(cost_poc))
        self.lbl_sia.set(self._fmt(cost_sia))
        self.lbl_nas.set(self._fmt(cost_nas))
        self.lbl_total.set(self._fmt(total))

    def _save_row(self):
        import pandas as pd
        from tkinter import messagebox
        path = self._get_complexes_path()
        if not path:
            messagebox.showwarning("Zapis", "Najpierw wskaż plik 'Kompleksy ...csv' w zakładce Kompleksy.", parent=self)
            return

        # docelowy porządek nagłówków (z nową kolumną)
        HEADERS = [
            "Reprezentacja","Kraj","Miasto","Miejsca dla kibicow","OS","Ig","Kx",
            "Tw","Kk","Ks","Poc","Sia","Nas","Typ inwestycji"
        ]

        # wczytaj istniejący CSV (liberalnie), albo załóż pusty z nagłówkami
        try:
            df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8", engine="python")
        except Exception:
            try:
                df = pd.read_csv(path, sep=";", dtype=str, encoding="cp1250", engine="python")
            except Exception:
                df = pd.DataFrame(columns=HEADERS)

        # upewnij się, że kolumna istnieje nawet w starych plikach
        if "Typ inwestycji" not in df.columns:
            df["Typ inwestycji"] = pd.NA

        # przygotuj wiersz
        row = {
            "Reprezentacja": self.var_rep.get().strip(),
            "Kraj": self.var_nat.get().strip().upper(),
            "Miasto": self.var_city.get().strip(),
            "Miejsca dla kibicow": str(int(self.var_seats.get() or 0)),
            "OS": str(int(self.var_os.get() or 0)),
            "Ig": str(int(self.var_ig.get() or 0)),
            "Kx": self.var_kx.get().strip(),
            "Tw": self.var_tw.get().strip(),
            "Kk": self.var_kk.get().strip(),
            "Ks": self.var_ks.get().strip(),
            "Poc": self.var_poc.get().strip(),
            "Sia": self.var_sia.get().strip(),
            "Nas": self.var_nas.get().strip(),
            "Typ inwestycji": self._investment_type_text(),
        }

        # jeśli w pliku brakuje którejś kolumny z HEADERS → dodaj ją,
        # a dla braków w row ustaw NaN (żeby concat nie mieszał)
        for c in HEADERS:
            if c not in df.columns:
                df[c] = pd.NA
            if c not in row:
                row[c] = pd.NA

        # aktualizacja/dodanie rekordu (klucz: Kraj + Miasto)
        key_mask = (
            df.get("Kraj","").astype(str).str.upper().eq(row["Kraj"]) &
            df.get("Miasto","").astype(str).str.strip().str.casefold().eq(row["Miasto"].casefold())
        )
        if hasattr(key_mask, "any") and key_mask.any():
            df.loc[key_mask, list(row.keys())] = list(row.values())
            op = "Zaktualizowano istniejący obiekt."
        else:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            op = "Dodano nowy obiekt."

        # uporządkuj kolumny i zapisz
        ordered = [c for c in HEADERS if c in df.columns] + [c for c in df.columns if c not in HEADERS]
        df = df[ordered]
        df.to_csv(path, sep=";", index=False, encoding="utf-8")

        messagebox.showinfo("Zapis", f"{op}\nPlik: {path}", parent=self)

        # odśwież widok Kompleksów (jeśli słuchasz eventu w zakładce)
        try:
            self.event_generate("<<HILLS_COMPLEXES_REFRESH>>")
        except Exception:
            pass

# -----------------------------
# Helper: Treeview CSV viewer (Skocznie)
# -----------------------------
class CsvViewer(ttk.Frame):
    """Treeview CSV viewer z flagami w kolumnie #0."""
    def __init__(self, parent, title_path: str, default_path: Path | None = None, flags_dir: Path | None = None):
        super().__init__(parent)
        self.var_path = tk.StringVar(value=str(default_path or ""))
        self._df: pd.DataFrame | None = None
        self._sort_state: dict[str, bool] = {}
        self._flag_cache: dict[str, tk.PhotoImage] = {}
        self._flags_dir = flags_dir
        self._flag_gap = "\u2003"  # odstęp

        # Pasek
        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(bar, text=title_path).pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.var_path, width=60).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(bar, text="Wybierz…", command=self._pick_file).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="Odśwież", command=self.refresh).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Nowy sezon →", command=self._kopiuj_na_nowy_sezon).pack(side=tk.LEFT, padx=6)

        # Tabela
        wrap = ttk.Frame(self); wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        self.tree = ttk.Treeview(wrap, columns=(), show="tree headings")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)
        self.tree.heading("#0", text="Reprezentacja")

        self.refresh()

    def _kopiuj_na_nowy_sezon(self):
        """
        Kopiuje plik Skocznie S<X>.csv z folderu ./S<X>/ do ./S<X+1>/,
        zmienia mu nazwę na Skocznie S<X+1>.csv i obcina 'Miejsca dla kibiców'
        o 5% dla każdej skoczni, która ma > 20000 miejsc.
        Wynik zaokrągla do 25 (np. 50000 * 0.95 = 47500 → zaokrąglone do 47500).
        """
        import re as _re2
        from pathlib import Path
        from tkinter import messagebox

        cur_path = Path(self.var_path.get().strip())
        if not cur_path.is_file():
            messagebox.showerror("Błąd", f"Nie znaleziono pliku:\n{cur_path.absolute()}")
            return

        # Wykryj numer sezonu z nazwy pliku lub folderu nadrzędnego
        # np. "./S51/Skocznie S51.csv" → S51 → next = S51
        match = _re2.search(r"S(\d+)", str(cur_path))
        if not match:
            messagebox.showerror("Błąd", "Nie udało się wykryć numeru sezonu ze ścieżki pliku.")
            return
        cur_num  = int(match.group(1))
        next_num = cur_num + 1
        cur_tag  = f"S{cur_num}"
        next_tag = f"S{next_num}"

        # Folder docelowy
        next_dir = cur_path.parent.parent / next_tag
        next_dir.mkdir(parents=True, exist_ok=True)
        dst_path = next_dir / f"Skocznie {next_tag}.csv"

        # Wczytaj plik (zachowaj kodowanie cp1250 jak oryginał)
        try:
            df = pd.read_csv(cur_path, sep=";", encoding="cp1250", dtype=str)
        except Exception:
            try:
                df = pd.read_csv(cur_path, sep=None, engine="python", encoding="utf-8-sig", dtype=str)
            except Exception as e:
                messagebox.showerror("Błąd odczytu", str(e))
                return

        # Znajdź kolumnę "Miejsca dla kibiców" (tolerancja na kodowanie znaków)
        col_mdk = None
        for c in df.columns:
            if "miejsca" in c.lower():
                col_mdk = c
                break
        if col_mdk is None:
            messagebox.showerror("Błąd", "Nie znaleziono kolumny 'Miejsca dla kibiców' w pliku.")
            return

        # Konwersja: usuń spacje-separator-tysięcy, parsuj, zastosuj -5% dla >20000
        def parse_capacity(val):
            """Parsuje '36 100' lub '36100' → 36100. Zwraca float lub None."""
            try:
                return float(str(val).replace(" ", "").replace(" ", "").replace(" ", "").replace(",", "."))
            except Exception:
                return None

        def format_capacity(val):
            """Formatuje liczbę z powrotem ze spacją jako sep. tysięcy: 47500 → '47 500'."""
            try:
                n = int(round(val))
                # Formatuj z separatorem spacji co 3 cyfry
                s = f"{n:,}".replace(",", " ")  # unicode non-breaking space jak w oryginale
                # Sprawdź jak oryginał formatuje – użyj zwykłej spacji
                return f"{n:,}".replace(",", " ")
            except Exception:
                return str(val)

        changed = 0
        new_vals = []
        for v in df[col_mdk]:
            num = parse_capacity(v)
            if num is not None and num > 20000:
                new_num = num * 0.95
                # Zaokrągl do najbliższych 25
                new_num = round(new_num / 25) * 25
                new_vals.append(format_capacity(new_num))
                changed += 1
            else:
                new_vals.append(str(v) if pd.notna(v) else "")

        df[col_mdk] = new_vals

        # Zapisz z tym samym kodowaniem co oryginał
        try:
            df.to_csv(dst_path, sep=";", index=False, encoding="cp1250")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e))
            return

        messagebox.showinfo(
            "Nowy sezon – gotowe",
            f"Plik zapisany jako:\n{dst_path.absolute()}\n\n"
            f"Skocznie z obciętą pojemnością (> 20 000 → −5%): {changed}"
        )

        # Ustaw ścieżkę i odśwież widok na nowy plik
        self.var_path.set(str(dst_path))
        self.refresh()

    def _pick_file(self):
        p = filedialog.askopenfilename(title="Wybierz plik CSV", filetypes=[("CSV","*.csv"),("Wszystkie pliki","*.*")])
        if p:
            self.var_path.set(p); self.refresh()

    def refresh(self):
        path_str = self.var_path.get().strip()
        path = Path(path_str) if path_str else None
        if not path or not path.exists():
            try:
                app_dir = Path(__file__).resolve().parent
            except Exception:
                app_dir = Path(".")
            fallback = app_dir / "./S51/Skocznie S51.csv"
            if fallback.exists():
                path = fallback; self.var_path.set(str(path))

        try:
            df = self._read_csv(path) if path else pd.DataFrame()
        except Exception as e:
            df = pd.DataFrame(); messagebox.showerror("Błąd odczytu CSV", str(e), parent=self)

        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.copy()
            df.columns = [str(c).strip() for c in df.columns]
            # wywal NaN / <NA> i zamień wszystko na ładne stringi
            df = df.where(pd.notna(df), "")
            for c in df.columns:
                df[c] = df[c].map(lambda x: str(x).strip())

        self._df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self._sort_state.clear()
        self._fill_table(self._df)

    def _read_csv(self, path: Path) -> pd.DataFrame:
        if not path or not Path(path).exists():
            return pd.DataFrame()
        for args in ({}, {"sep":";"}, {"sep":";","encoding":"cp1250"}, {"sep":";","encoding":"latin1"}):
            try:
                return pd.read_csv(path, **args)
            except Exception:
                continue
        return pd.DataFrame()

    # --- flag helpers ---
    def _extract_nat_code(self, value: str) -> str | None:
        if not value: return None
        v = str(value).strip()
        if re.fullmatch(r"[A-Za-z]{3}", v): return v.upper()
        m = re.search(r"\b([A-Z]{3})\b", v.upper())
        return m.group(1) if m else None

    def _guess_nat_code(self, row: pd.Series, rep_col: str | None, cols: list[str]) -> str | None:
        for cand in ["Kraj","NAT","ISO3","ISO-3","Kod","Code"]:
            for c in cols:
                if str(c).strip().lower() == cand.lower():
                    v = row.get(c, None)
                    if v is not None:
                        c3 = self._extract_nat_code(str(v))
                        if c3: return c3
        rep_val = None if rep_col is None else row.get(rep_col, None)
        return self._extract_nat_code("" if rep_val is None else str(rep_val))

    def _load_flag(self, nat_code: str) -> tk.PhotoImage | None:
        if not self._flags_dir or not nat_code: return None
        code = nat_code.upper()
        if code in self._flag_cache: return self._flag_cache[code]
        for p in [self._flags_dir/f"{code}.png", self._flags_dir/f"{code}.gif", self._flags_dir/code.lower()/f"{code}.png"]:
            if p.exists():
                try:
                    img = tk.PhotoImage(file=str(p))
                    self._flag_cache[code] = img
                    return img
                except Exception:
                    continue
        self._flag_cache[code] = None
        return None

    # --- table ---
    def _fill_table(self, df: pd.DataFrame):
        for iid in self.tree.get_children(): self.tree.delete(iid)
        if df is None or df.empty:
            self.tree["columns"] = []; self.tree.heading("#0", text="Reprezentacja"); return

        cols = list(df.columns)
        rep_col = None
        for cand in FLAG_COL_CANDIDATES:
            for c in cols:
                if str(c).strip().lower() == cand.lower():
                    rep_col = c; break
            if rep_col: break

        header_cols = [c for c in cols if c != rep_col] if rep_col else cols
        self.tree["columns"] = header_cols

        if rep_col:
            self.tree.heading("#0", text=str(rep_col)); self.tree.column("#0", width=180, stretch=True, anchor="w")
        else:
            self.tree.heading("#0", text=""); self.tree.column("#0", width=20, stretch=False, anchor="w")

        for c in header_cols:
            self.tree.heading(c, text=c, command=lambda col=c: self._on_sort_click(col))
            self.tree.column(c, width=max(80, int(8.5*len(str(c)))), stretch=True, anchor="w")

        for _, row in df.iterrows():
            values = ["" if pd.isna(row.get(c,"")) else row.get(c,"") for c in header_cols]
            if rep_col:
                rep_val = "" if pd.isna(row.get(rep_col,"")) else row.get(rep_col,"")
                code = self._guess_nat_code(row, rep_col, cols)
                flag = self._load_flag(code) if code else None
                txt = "" if rep_val is None else str(rep_val)
                if flag is not None: txt = f"{self._flag_gap}{txt}"
                kwargs = {"text": txt, "values": tuple("" if v is None else str(v) for v in values)}
                if flag is not None: kwargs["image"] = flag
                self.tree.insert("", "end", **kwargs)
            else:
                self.tree.insert("", "end", text="", values=tuple("" if v is None else str(v) for v in values))

        # auto width
        try:
            fnt = tkfont.nametofont("TkDefaultFont")
            sample = self.tree.get_children()[:200]
            if rep_col:
                w = fnt.measure(str(rep_col)) + 48
                for iid in sample: w = max(w, fnt.measure(str(self.tree.item(iid,"text"))) + 48)
                self.tree.column("#0", width=min(w, 300))
            for c in header_cols:
                w = fnt.measure(c) + 28
                for iid in sample: w = max(w, fnt.measure(str(self.tree.set(iid,c))) + 28)
                self.tree.column(c, width=min(w, 460))
        except Exception:
            pass

    def _on_sort_click(self, col: str):
        if self._df is None or self._df.empty: return
        asc = not self._sort_state.get(col, True)
        df = self._df.copy()
        try:
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().any(): df[col] = s
        except Exception:
            pass
        try:
            df = df.sort_values(by=col, ascending=asc, kind="mergesort")
        except Exception:
            return
        self._sort_state[col] = asc
        self._fill_table(df)

# --------------------------------
# Infrastructure Canvas Grid (per-cell background)
# --------------------------------
class InfraCanvasGrid(ttk.Frame):
    """Siatka na Canvasie z kolorowaniem komórek 0..5 (-→0)."""
    PALETTE = {
        0: "#f2f2f2",  # szare
        1: "#ffb3b3",  # czerwone
        2: "#ffd1a6",  # pomarańczowe
        3: "#ffe680",  # żółte
        4: "#c6f3c6",  # jasnozielone
        5: "#9de69d",  # zielone
    }

    def __init__(self, parent, title_path: str, default_path: Path | None = None, flags_dir: Path | None = None):
        super().__init__(parent)
        self.var_path = tk.StringVar(value=str(default_path or ""))
        self.flags_dir = flags_dir
        self.flag_cache: dict[str, tk.PhotoImage] = {}
        self.df: pd.DataFrame | None = None
        self.scale_cols: list[str] = []
        self.rep_col: str | None = None

        # Pasek
        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(bar, text=title_path).pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.var_path, width=60).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(bar, text="Wybierz…", command=self._pick_file).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="Odśwież", command=self.refresh).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Nowy sezon →", command=self._kopiuj_na_nowy_sezon).pack(side=tk.LEFT, padx=6)

        # Canvas + scroll
        wrap = ttk.Frame(self); wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        self.canvas = tk.Canvas(wrap, highlightthickness=0)
        self.vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.vsb.configure(command=self.canvas.yview)
        self.hsb.configure(command=self.canvas.xview)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)

        self.canvas.bind("<Configure>", lambda e: self._update_scrollregion())
        self.canvas.bind("<Enter>", lambda e: self._mousewheel_bind(True))
        self.canvas.bind("<Leave>", lambda e: self._mousewheel_bind(False))

        self.refresh()

    # --- IO ---
    def _pick_file(self):
        p = filedialog.askopenfilename(title="Wybierz plik CSV", filetypes=[("CSV","*.csv"),("Wszystkie pliki","*.*")])
        if p: self.var_path.set(p); self.refresh()

    def refresh(self):
        path_str = self.var_path.get().strip()
        path = Path(path_str) if path_str else None
        if not path or not path.exists():
            try:
                app_dir = Path(__file__).resolve().parent
            except Exception:
                app_dir = Path(".")
            fallback = app_dir / "Infrastruktura S51.csv"
            if fallback.exists():
                path = fallback; self.var_path.set(str(path))

        try:
            df = self._read_csv(path) if path else pd.DataFrame()
        except Exception as e:
            df = pd.DataFrame(); messagebox.showerror("Błąd odczytu CSV", str(e), parent=self)

        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.copy()
            # przytnij nagłówki
            df.columns = [str(c).strip() for c in df.columns]
            # pozbądź się NaN / <NA> → puste
            df = df.where(pd.notna(df), "")
            # wszystko jako string, bez zbędnych spacji
            for c in df.columns:
                df[c] = df[c].map(lambda x: str(x).strip())

        self.df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self._detect_columns()
        self._redraw()


    def _read_csv(self, path: Path) -> pd.DataFrame:
        if not path or not Path(path).exists(): return pd.DataFrame()
        for args in ({}, {"sep":";"}, {"sep":";","encoding":"cp1250"}, {"sep":";","encoding":"latin1"}):
            try:
                return pd.read_csv(path, **args)
            except Exception:
                continue
        return pd.DataFrame()

    def _kopiuj_na_nowy_sezon(self):
        """
        Przenosi plik Infrastruktura S<X>.csv z folderu ./S<X>/ do ./S<X+1>/
        i zmienia mu nazwę na Infrastruktura S<X+1>.csv.
        Bez żadnych modyfikacji zawartości - czysta kopia + zmiana nazwy
        (w przeciwieństwie do zakładki 'Skocznie', gdzie dodatkowo
        przeliczana jest pojemność widowni).
        """
        import re as _re2
        import shutil as _shutil
        from pathlib import Path as _Path
        from tkinter import messagebox

        cur_path = _Path(self.var_path.get().strip())
        if not cur_path.is_file():
            messagebox.showerror("Błąd", f"Nie znaleziono pliku:\n{cur_path.absolute()}")
            return

        # Wykryj numer sezonu z nazwy pliku / folderu, np. "./S51/Infrastruktura S51.csv" -> S51
        match = _re2.search(r"S(\d+)", str(cur_path))
        if not match:
            messagebox.showerror("Błąd", "Nie udało się wykryć numeru sezonu ze ścieżki pliku.")
            return
        cur_num  = int(match.group(1))
        next_num = cur_num + 1
        cur_tag  = f"S{cur_num}"
        next_tag = f"S{next_num}"

        # Folder docelowy (jak w 'Skocznie')
        next_dir = cur_path.parent.parent / next_tag
        next_dir.mkdir(parents=True, exist_ok=True)
        dst_path = next_dir / f"Infrastruktura {next_tag}.csv"

        try:
            _shutil.copyfile(cur_path, dst_path)
        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e))
            return

        messagebox.showinfo(
            "Nowy sezon – gotowe",
            f"Plik zapisany jako:\n{dst_path.absolute()}\n\n"
            f"Plik został przeniesiony bez żadnych zmian (tylko zmiana nazwy: {cur_tag} → {next_tag})."
        )

        # Ustaw ścieżkę i odśwież widok na nowy plik
        self.var_path.set(str(dst_path))
        self.refresh()

    # --- detect scale cols ---
    def _detect_columns(self):
        self.scale_cols = []
        self.rep_col = None
        if self.df is None or self.df.empty: return
        cols = list(self.df.columns)
        for cand in FLAG_COL_CANDIDATES:
            for c in cols:
                if str(c).strip().lower() == cand.lower():
                    self.rep_col = c; break
            if self.rep_col: break
        sample = self.df.head(400)
        for c in cols:
            try:
                s = sample[c].astype(str).str.strip().replace({"-":"0","–":"0","—":"0"})
                nums = pd.to_numeric(s, errors="coerce")
                ok = nums.dropna().between(0,5).all()
                if ok and nums.notna().sum() >= max(3, int(len(sample)*0.1)):
                    self.scale_cols.append(c)
            except Exception:
                continue

    # --- drawing ---
    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-event.delta/120), "units")

    def _flag_image(self, code: str) -> tk.PhotoImage | None:
        if not self.flags_dir or not code: return None
        code = code.upper()
        if code in self.flag_cache: return self.flag_cache[code]
        for p in [self.flags_dir/f"{code}.png", self.flags_dir/f"{code}.gif", self.flags_dir/code.lower()/f"{code}.png"]:
            if p.exists():
                try:
                    img = tk.PhotoImage(file=str(p))
                    self.flag_cache[code] = img; return img
                except Exception:
                    continue
        self.flag_cache[code] = None
        return None

    def _nat_from_row(self, row: pd.Series, cols: list[str]) -> str | None:
        for cand in ["Kraj","NAT","ISO3","ISO-3","Kod","Code"]:
            for c in cols:
                if str(c).strip().lower() == cand.lower():
                    v = row.get(c, None)
                    if v and isinstance(v,str) and len(v.strip())>=3:
                        v2 = re.findall(r"[A-Za-z]{3}", v.strip().upper())
                        if v2: return v2[0]
        if self.rep_col:
            v = str(row.get(self.rep_col,"")).strip().upper()
            v2 = re.findall(r"[A-Za-z]{3}", v)
            if v2: return v2[0]
        return None

    def _redraw(self):
        self.canvas.delete("all")
        if self.df is None or self.df.empty:
            self.canvas.configure(scrollregion=(0,0,0,0)); return

        fnt = tkfont.nametofont("TkDefaultFont")
        row_h = max(int(fnt.metrics("linespace")) + 8, 24)
        cols = list(self.df.columns)

        # kol widths
        widths = {}
        min_w = 80
        for c in cols:
            if c in self.scale_cols:
                widths[c] = 110
            else:
                w = fnt.measure(c) + 24
                for _, r in self.df.head(100).iterrows():
                    text = str(r.get(c,""))
                    w = max(w, fnt.measure(text) + 24)
                # Sprawdzamy, czy aktualna kolumna to kolumna reprezentacji
                if c == self.rep_col:
                    # Tutaj ustawiamy większy limit (np. 180px minimum i 500px maksimum)
                    widths[c] = max(200, min(w, 520))
                else:
                    # Dla pozostałych kolumn zostawiamy Twoje oryginalne ustawienia
                    widths[c] = max(min_w, min(w, 200))

        # nagłówki
        x = 0; y = 0
        for c in cols:
            self.canvas.create_rectangle(x, y, x+widths[c], y+row_h, fill="#e9ecef", outline="#d0d4d9")
            self.canvas.create_text(x+6, y+row_h/2, text=c.upper(), anchor="w", font=fnt)
            x += widths[c]
        y += row_h

        # wiersze
        for _, row in self.df.iterrows():
            x = 0
            self.canvas.create_rectangle(0, y, sum(widths.values()), y+row_h, fill="#ffffff", outline="")
            for c in cols:
                val = row.get(c, "")
                self.canvas.create_rectangle(x, y, x+widths[c], y+row_h, fill="", outline="#e5e5e5")

                if c in self.scale_cols:
                    try:
                        if str(val).strip() in {"-","–","—"}: n = 0
                        else: n = int(float(val))
                    except Exception:
                        n = 0
                    n = max(0, min(5, n))
                    color = self.PALETTE.get(n, "#f2f2f2")
                    self.canvas.create_rectangle(x+1, y+1, x+widths[c]-1, y+row_h-1, fill=color, outline="")
                    self.canvas.create_text(x+widths[c]-8, y+row_h/2, text=str(n), anchor="e", font=fnt)
                else:
                    if self.rep_col and c == self.rep_col:
                        code = self._nat_from_row(row, cols)
                        flag = self._flag_image(code) if code else None
                        if flag:
                            self.canvas.create_image(x+6, y+row_h/2, image=flag, anchor="w")
                            self.canvas.create_text(x+6+flag.width()+6, y+row_h/2, text=str(val), anchor="w", font=fnt)
                        else:
                            self.canvas.create_text(x+6, y+row_h/2, text=str(val), anchor="w", font=fnt)
                    else:
                        self.canvas.create_text(x+6, y+row_h/2, text=str(val), anchor="w", font=fnt)
                x += widths[c]
            y += row_h

        total_w = sum(widths.values())
        self.canvas.configure(scrollregion=(0, 0, total_w, y))

        self.canvas.update_idletasks()
        self._update_scrollregion()

    def _update_scrollregion(self):
        # upewnij się, że masz atrybuty z rozmiarem treści; jeśli nie, policz z buforów rysowania
        w = getattr(self, "_content_w", self.canvas.bbox("all")[2] if self.canvas.bbox("all") else 0)
        h = getattr(self, "_content_h", self.canvas.bbox("all")[3] if self.canvas.bbox("all") else 0)
        try:
            self.canvas.configure(scrollregion=(0, 0, max(w, 0), max(h, 0)))
        except Exception:
            pass

    def _mousewheel_bind(self, enable: bool):
        # Windows/Mac: <MouseWheel>; Linux: <Button-4/5>
        if enable:
            self.canvas.focus_set()  # ważne na Windows/Mac
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
            self.canvas.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel, add="+")
            self.canvas.bind_all("<Button-4>", self._on_linux_wheel_up, add="+")
            self.canvas.bind_all("<Button-5>", self._on_linux_wheel_down, add="+")
        else:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Shift-MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        # Windows: delta = ±120; Mac: różna skala – normalizujemy
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def _on_shift_mousewheel(self, event):
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.canvas.xview_scroll(delta, "units")

    def _on_linux_wheel_up(self, event):
        self.canvas.yview_scroll(-1, "units")

    def _on_linux_wheel_down(self, event):
        self.canvas.yview_scroll(1, "units")

# --- Canvas grid dla zakładki "Skocznie" (bez skali 0..5) ---
class HillsCanvasGrid(InfraCanvasGrid):
    def __init__(self, parent, title_path: str, default_path=None, flags_dir=None):
        super().__init__(parent, title_path, default_path, flags_dir)
        # Przycisk "Nowy sezon →" jest już dodawany w klasie bazowej (InfraCanvasGrid),
        # a wywoła on poniższą (nadpisaną) wersję _kopiuj_na_nowy_sezon dzięki polimorfizmowi.

    def _kopiuj_na_nowy_sezon(self):
        """
        Kopiuje Skocznie S<X>.csv z ./S<X>/ do ./S<X+1>/
        jako Skocznie S<X+1>.csv i obcina Miejsca dla kibiców
        o 5% dla każdej skoczni z > 20 000 miejsc (zaokrąglenie do 25).
        """
        import re as _re2
        from pathlib import Path
        from tkinter import messagebox

        cur_path = Path(self.var_path.get().strip())
        if not cur_path.is_file():
            messagebox.showerror("Błąd", f"Nie znaleziono pliku:\n{cur_path.absolute()}")
            return

        match = _re2.search(r"S(\d+)", str(cur_path))
        if not match:
            messagebox.showerror("Błąd", "Nie udało się wykryć numeru sezonu ze ścieżki pliku.")
            return
        cur_num  = int(match.group(1))
        next_num = cur_num + 1
        cur_tag  = f"S{cur_num}"
        next_tag = f"S{next_num}"

        next_dir = cur_path.parent.parent / next_tag
        next_dir.mkdir(parents=True, exist_ok=True)
        dst_path = next_dir / f"Skocznie {next_tag}.csv"

        try:
            df = pd.read_csv(cur_path, sep=";", encoding="cp1250", dtype=str)
        except Exception:
            try:
                df = pd.read_csv(cur_path, sep=None, engine="python", encoding="utf-8-sig", dtype=str)
            except Exception as e:
                messagebox.showerror("Błąd odczytu", str(e))
                return

        col_mdk = next((c for c in df.columns if "miejsca" in c.lower()), None)
        if col_mdk is None:
            messagebox.showerror("Błąd", "Nie znaleziono kolumny 'Miejsca dla kibiców' w pliku.")
            return

        def parse_cap(val):
            try:
                return float(str(val).replace("\u00a0","").replace(" ","").replace("\xa0","").replace(",","."))
            except Exception:
                return None

        def fmt_cap(val):
            try:
                n = int(round(val))
                return f"{n:,}".replace(",", " ")
            except Exception:
                return str(val)

        changed = 0
        new_vals = []
        for v in df[col_mdk]:
            num = parse_cap(v)
            if num is not None and num > 20000:
                new_vals.append(fmt_cap(round(num * 0.95 / 25) * 25))
                changed += 1
            else:
                new_vals.append(str(v) if pd.notna(v) else "")
        df[col_mdk] = new_vals

        try:
            df.to_csv(dst_path, sep=";", index=False, encoding="cp1250")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e))
            return

        messagebox.showinfo(
            "Nowy sezon – gotowe",
            f"Plik zapisany:\n{dst_path.absolute()}\n\n"
            f"Skocznie z obciętą pojemnością (> 20 000 → −5%): {changed}"
        )
        self.var_path.set(str(dst_path))
        self.refresh()

    def _detect_columns(self):
        """
        Dla 'Skoczni' nie używamy kolorowej skali 0..5 – pokazujemy neutralne tło.
        Zachowujemy wykrywanie kolumny reprezentacji (do flag) jak w klasie bazowej.
        """
        self.scale_cols = []   # brak kolumn skalowanych (neutralne tło)
        self.rep_col = None
        if self.df is None or self.df.empty:
            return
        cols = list(self.df.columns)
        # znajdź kolumnę z reprezentacją (Kraj/NAT/…)
        for cand in FLAG_COL_CANDIDATES:
            for c in cols:
                if str(c).strip().lower() == cand.lower():
                    self.rep_col = c
                    break
            if self.rep_col:
                break

# -----------------------------
# Main tab with two sub-tabs
# -----------------------------
class HillsTab(ttk.Frame):
    def _auto_export_build_costs(self):
        # Pobieramy to co przed chwilą zapisał _recalc_build_costs do cache
        df_sum = self._buildcost_cache.get("by_country")
        if df_sum is not None and not df_sum.empty:
            try:
                # Sortujemy i zapisujemy
                df_to_save = df_sum.sort_values("Suma", ascending=False)
                output_path = Path("S51/Koszty rozbudowy skoczni S51.csv")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                df_to_save.to_csv(output_path, sep=";", index=False, encoding="cp1250")
            except Exception as e:
                print(f"Błąd auto-eksportu: {e}")
                
    def _export_build_costs_to_csv(self):
        df_sum = self._buildcost_cache.get("by_country")
        if df_sum is not None and not df_sum.empty:
            try:
                df_to_save = df_sum.copy()
                df_to_save = df_to_save.sort_values("Suma", ascending=False)
                output_path = Path("S51/Koszty rozbudowy skoczni S51.csv")
                df_to_save.to_csv(output_path, sep=";", index=False, encoding="cp1250")
                messagebox.showinfo("Eksport", f"Wyeksportowano do:\n{output_path}")
            except Exception as e:
                messagebox.showerror("Błąd", str(e))
        else:
            messagebox.showwarning("Eksport", "Brak danych. Kliknij najpierw 'Przelicz'.")

    def _recalc_build_costs(self):
        """Metoda klasy przeliczająca koszty i wymuszająca eksport."""
        path_str = self._buildlog_path_var.get().strip()
        if not path_str:
            messagebox.showwarning("Koszty budowy", "Podaj ścieżkę do pliku Rozbudowa S51.csv.")
            return
        
        p = Path(path_str)
        if not p.exists():
            self._buildcost_cache = {"rows": pd.DataFrame(), "by_country": pd.DataFrame()}
            self._render_build_costs()
            return

        df_log = self._read_build_log(p) # Upewnij się, że ta metoda też ma self.
        if df_log is None or getattr(df_log, "empty", True):
            self._buildcost_cache = {"rows": pd.DataFrame(), "by_country": pd.DataFrame()}
            self._render_build_costs()
            return

        inv, by_nat = compute_build_extend_costs(df_log)
        self._buildcost_cache = {"rows": inv, "by_country": by_nat}
        self._render_build_costs()
        
        # AUTOMATYCZNY EKSPORT PO KAŻDYM PRZELICZENIU
        self._auto_export_build_costs()

    def _render_build_costs(self):
        mode = self._buildcost_view.get() or "Inwestycje – lista"
        df_rows = self._buildcost_cache.get("rows", pd.DataFrame())
        df_nat = self._buildcost_cache.get("by_country", pd.DataFrame())

        if mode == "Kraje – suma":
            df = df_nat.copy()
            if not df.empty and "Suma" in df.columns:
                df = _fmt_eur(df, ["Suma"])
            # TUTAJ: używamy self.
            self._tree_simple_build_custom(self._buildcost_wrap, df, ["Kraj", "Suma"], True, True)
        else:
            df = df_rows.copy()
            if not df.empty and "Koszt" in df.columns:
                df = _fmt_eur(df, ["Koszt"])
            # TUTAJ: używamy self.
            self._tree_simple_build_custom(self._buildcost_wrap, df, 
                ["TS", "Tryb", "Reprezentacja", "Kraj", "Miasto", "Skocznia", "Typ inwestycji", "Koszt"], True, True)
            
    # Dodaj to jako samodzielną metodę klasy HillsTab (poziom wcięcia ten sam co __init__)
    def _read_build_log(self, path: Path):
        import pandas as pd
        last_err = None
        for enc in ("utf-8", "utf-8-sig", "cp1250", "latin1"):
            try:
                df = pd.read_csv(path, sep=";", engine="python", encoding=enc)
                print(f"DEBUG ROZBUDOWA READ OK: {path} enc={enc} shape={getattr(df, 'shape', None)}")
                return df
            except Exception as e:
                last_err = e
                continue
        print("DEBUG ROZBUDOWA READ FAIL:", path, "->", last_err)
        return None

    def _tree_simple_build_custom(self, parent, df_data: pd.DataFrame, cols, stretch_last=False, with_flags=False):
            # wyczyść kontener
            for w in parent.winfo_children():
                w.destroy()

            container = ttk.Frame(parent)
            container.pack(fill="both", expand=True)
            yscroll = ttk.Scrollbar(container, orient="vertical")
            xscroll = ttk.Scrollbar(container, orient="horizontal")

            use_tree_col = with_flags and len(cols) > 0 and cols[0] == "Kraj"
            show_mode = "tree headings" if use_tree_col else "headings"

            tv = ttk.Treeview(
                container,
                columns=(cols if not use_tree_col else cols[1:]),
                show=show_mode,
                yscrollcommand=yscroll.set,
                xscrollcommand=xscroll.set,
                height=18,
            )
            tv.img_refs = []

            yscroll.config(command=tv.yview)
            xscroll.config(command=tv.xview)
            tv.grid(row=0, column=0, sticky="nsew")
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll.grid(row=1, column=0, sticky="ew")
            container.rowconfigure(0, weight=1)
            container.columnconfigure(0, weight=1)

            if use_tree_col:
                tv.heading("#0", text="Kraj")
                tv.column("#0", width=140, anchor="w")
                head_cols = cols[1:]
            else:
                head_cols = cols

            for c in head_cols:
                tv.heading(c, text=c)
                tv.column(c, width=120, anchor="center")
            if stretch_last and head_cols:
                tv.column(head_cols[-1], width=160, anchor="center")

            if df_data is None or df_data.empty:
                return tv

            # upewnij się, że istnieją kolumny
            for c in cols:
                if c not in df_data.columns:
                    df_data[c] = ""

            if use_tree_col:
                # wersja z flagami
                for _, row in df_data[cols].iterrows():
                    code = str(row.get("Kraj", "") or "")
                    flags_dir = getattr(self, "_flags_dir", None)
                    img = _get_flag_image(flags_dir, code)
                    vals = tuple(
                        "" if pd.isna(row.get(c, "")) else str(row.get(c, ""))
                        for c in cols[1:]
                    )
                    kwargs = {"text": code, "values": vals}
                    if img is not None:
                        kwargs["image"] = img
                        tv.img_refs.append(img)
                    tv.insert("", "end", **kwargs)
            else:
                # bez flag
                for _, row in df_data[cols].iterrows():
                    vals = [
                        "" if pd.isna(row.get(c, "")) else str(row.get(c, ""))
                        for c in cols
                    ]
                    tv.insert("", "end", values=vals)

            return tv

    def __init__(self, parent,
                 default_hills: Path | None = None,
                 default_infra: Path | None = None,
                 flags_dir: Path | None = None,
                 default_complexes: Path | None = None):
        super().__init__(parent)
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True)

        # Skocznie (Treeview)
        tab_h = ttk.Frame(nb, name="skocznie")
        nb.add(tab_h, text="Skocznie")
        self.hills_viewer = HillsCanvasGrid(tab_h, "Plik skoczni (CSV):", default_hills, flags_dir)
        self.hills_viewer.pack(fill="both", expand=True)

        # Kompleksy (tak samo jak Skocznie)
        tab_c = ttk.Frame(nb, name="kompleksy")
        # --- Kompleksy: podgląd z agregacji Skoczni ---
        self._complexes_wrap = ttk.Frame(tab_c)
        self._complexes_wrap.pack(fill="both", expand=True)

        nb.add(HillBuilderTab(nb, csv_path="S51/Skocznie S51.csv"), text="Budowa skoczni")


        def _render_complexes_tab():
            # wyczyść kontener
            for w in self._complexes_wrap.winfo_children():
                w.destroy()

            # toolbar
            bar = ttk.Frame(self._complexes_wrap)
            bar.pack(fill="x", padx=8, pady=(8, 4))
            ttk.Label(bar, text="Kompleksy (auto ze 'Skocznie')").pack(side="left")
            ttk.Button(
                bar, text="Odśwież",
                command=lambda: (_compute_if_needed(), _render_complexes_tab())
            ).pack(side="left", padx=8)

            # dane
            try:
                df_hills = getattr(self.hills_viewer, "df", None)
                if df_hills is None:
                    df_hills = getattr(self.hills_viewer, "_df", None)
            except Exception:
                df_hills = None
            df_src = build_complexes_from_hills(df_hills)

            # tabela
            wrap = ttk.Frame(self._complexes_wrap)
            wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

            # 1) Nie pokazujemy „Reprezentacja”; #0 = „Kraj” (z flagą)
            all_cols = list(df_src.columns) if not df_src.empty else [
                "Reprezentacja","Kraj","Miasto","Miejsca dla kibicow","OS","Ig","Kx","Tw","Kk","Ks","Poc","Sia","Nas"
            ]
            cols = [c for c in all_cols if c not in ("Reprezentacja", "Kraj")]  # wywal Reprezentacja, Kraj idzie do #0

            tv = ttk.Treeview(wrap, show="tree headings", columns=cols, height=18)
            vsb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
            hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tv.xview)
            tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tv.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            wrap.rowconfigure(0, weight=1)
            wrap.columnconfigure(0, weight=1)

            # #0 = „Kraj”
            tv.heading("#0", text="Kraj")
            tv.column("#0", width=140, anchor="w")

            # pozostałe nagłówki
            for c in cols:
                tv.heading(c, text=c)
                tv.column(c, width=120, anchor="center")

            # cache obrazków, żeby nie znikały
            _flag_cache = {}

            def _get_flag_cached(code: str):
                code = (code or "").strip().upper()
                if not code:
                    return None
                if code in _flag_cache:
                    return _flag_cache[code]
                img = _get_flag_image(self._flags_dir, code)  # helper z góry pliku
                _flag_cache[code] = img
                return img

            # wstawianie wierszy: tekst i flaga w #0, wartości w kolumnach
            if not df_src.empty:
                for _, r in df_src.iterrows():
                    kraj = str(r.get("Kraj", "") or "").upper()
                    img = _get_flag_cached(kraj)
                    values = []
                    for c in cols:
                        v = r.get(c, "")
                        try:
                            safe = "" if pd.isna(v) else str(v)
                        except (TypeError, ValueError):
                            safe = "" if v is None else str(v)
                        values.append(safe)
                    tv.insert("", "end", text=kraj, image=img, values=values)

        nb.add(tab_c, text="Kompleksy")

        # Infrastruktura (Canvas grid)
        tab_i = ttk.Frame(nb, name="infrastruktura")
        nb.add(tab_i, text="Infrastruktura")
        self.infra_viewer = InfraCanvasGrid(tab_i, "Plik infrastruktury (CSV):", default_infra, flags_dir)
        self.infra_viewer.pack(fill="both", expand=True)

        # Zakładka inwestycji w centra (ME/EK/IN/ED/ZY)
        tab_centers = ttk.Frame(nb, name="infra_centers")
        nb.add(tab_centers, text="Centra ME/EK/IN/ED/ŻY")
        self._build_infra_upgrade_tab(tab_centers)

        # Homologacje – warunki minimalne klas
        tab_homo = ttk.Frame(nb, name="homologacje")
        nb.add(tab_homo, text="Homologacje")
        self._build_homologations_tab(tab_homo)

        # --- Koszty budowy / rozbudowy (Rozbudowa S51.csv) ---
        tab_build_costs = ttk.Frame(nb, name="koszty_budowy")
        nb.add(tab_build_costs, text="Koszty budowy")

        from tkinter import filedialog, messagebox
        import pandas as _pd

        top_bc = ttk.Frame(tab_build_costs)
        top_bc.pack(fill="x", padx=8, pady=(8, 4))

        # domyślna ścieżka: S51/Rozbudowa S51.csv
        self._buildlog_path_var = tk.StringVar(
            value=str(Path("S51") / "Rozbudowa S51.csv")
        )

        ttk.Label(top_bc, text="Plik logu rozbudowy:").pack(side="left")
        ent_path = ttk.Entry(top_bc, textvariable=self._buildlog_path_var, width=50)
        ent_path.pack(side="left", padx=4)

        def _pick_buildlog():
            p = filedialog.askopenfilename(
                title="Wybierz Rozbudowa S51.csv",
                filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")]
            )
            if p:
                self._buildlog_path_var.set(p)
                self._recalc_build_costs()

        ttk.Button(top_bc, text="…", width=3, command=_pick_buildlog).pack(side="left", padx=(0, 6))

        ttk.Label(top_bc, text="Widok:").pack(side="left", padx=(8, 2))
        self._buildcost_view = tk.StringVar(value="Inwestycje – lista")
        cbo_view = ttk.Combobox(
            top_bc,
            textvariable=self._buildcost_view,
            state="readonly",
            values=["Inwestycje – lista", "Kraje – suma"],
            width=22,
        )
        cbo_view.pack(side="left")
        cbo_view.bind("<<ComboboxSelected>>", lambda e: self._render_build_costs())

        def _export_to_csv():
            mode = view_var.get()
            _compute_if_needed()

            if mode == "Kraje — suma":
                # Jeśli istnieje plik klasy operacyjnej, stosuj mnożniki
                op_path = Path(getattr(self, "_op_class_path", "S51/Klasa operacyjna S51.csv"))
                df_op = load_operational_classes(op_path)
                df_rows_cached = _cache.get("df_rows")
                if df_rows_cached is not None and not df_rows_cached.empty and not df_op.empty:
                    df_to_save = apply_operational_multipliers(df_rows_cached, df_op)
                    note = " (z klasą operacyjną)"
                else:
                    df_to_save = _cache["by_sum"]
                    note = ""
            else:
                export_map = {
                    "Kraje — rozbicie":       _cache["by_break"],
                    "Kraje — suma + liczba":  _cache["by_count"],
                    "Ranking":                _cache["ranking"],
                }
                df_to_save = export_map.get(mode)
                note = ""

            if df_to_save is not None and not df_to_save.empty:
                try:
                    # Definiujemy ścieżkę zapisu (w tym samym folderze co inne pliki S51)
                    output_path = Path("S51/Utrzymanie Skoczni S51.csv")
                    
                    # Zapisujemy dane z kodowaniem cp1250 (standard dla Excela w PL)
                    df_to_save.to_csv(output_path, sep=";", index=False, encoding="cp1250")
                    messagebox.showinfo("Eksport", f"Wyeksportowano{note} do:\n{output_path}")
                except Exception as e:
                    messagebox.showerror("Błąd eksportu", f"Nie udało się zapisać pliku: {e}")
            else:
                messagebox.showwarning("Eksport", "Brak danych do wyeksportowania.")
        
        ttk.Button(top_bc, text="Przelicz", command=self._recalc_build_costs).pack(side="right")
        ttk.Button(top_bc, text="Eksportuj Kraje (Suma)", command=self._export_build_costs_to_csv).pack(side="right", padx=6)
        
        self._buildcost_wrap = ttk.Frame(tab_build_costs)
        self._buildcost_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._buildcost_cache = {
            "rows": _pd.DataFrame(),
            "by_country": _pd.DataFrame(),
        }

        # --- Koszty rozbudowy Infrastruktury (Rozbudowa Infrastruktury S51.csv) ---
        tab_infra_costs = ttk.Frame(nb, name="koszty_infra")
        nb.add(tab_infra_costs, text="Koszty rozbudowy Infrastruktury")

        top_ic = ttk.Frame(tab_infra_costs)
        top_ic.pack(fill="x", padx=8, pady=(8, 4))

        # domyślna ścieżka do logu rozbudowy infrastruktury
        try:
            default_infra_log = Path("S51") / "Rozbudowa Infrastruktury S51.csv"
        except Exception:
            default_infra_log = Path("Rozbudowa Infrastruktury S51.csv")

        self._infralog_path_var = tk.StringVar(value=str(default_infra_log))

        ttk.Label(top_ic, text="Plik logu rozbudowy infrastruktury:").pack(side="left")
        ent_ic = ttk.Entry(top_ic, textvariable=self._infralog_path_var, width=50)
        ent_ic.pack(side="left", padx=4, fill="x", expand=True)

        def _pick_infralog():
            p = filedialog.askopenfilename(
                title="Wybierz Rozbudowa Infrastruktury S51.csv",
                filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")]
            )
            if p:
                self._infralog_path_var.set(p)
                _recalc_infra_costs()

        ttk.Button(top_ic, text="…", width=3, command=_pick_infralog).pack(side="left", padx=(0, 6))
        ttk.Button(top_ic, text="Przelicz", command=lambda: _recalc_infra_costs()).pack(side="right")

        self._infracost_wrap = ttk.Frame(tab_infra_costs)
        self._infracost_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # cache DF z rankingiem kosztów per kraj
        self._infracost_df = _pd.DataFrame()

        def _render_infra_costs():
            df = self._infracost_df
            if not isinstance(df, _pd.DataFrame) or df.empty:
                df = _pd.DataFrame(columns=["Kraj", "Suma"])
            else:
                if "Suma" in df.columns:
                    df = _fmt_eur(df, ["Suma"])

            self._tree_simple_build_custom(
                self._infracost_wrap,
                df,
                cols=["Kraj", "Suma"],
                stretch_last=True,
                with_flags=True,
            )

        def _read_infra_log(path: Path):
            import pandas as pd
            last_err = None
            for enc in ("utf-8", "utf-8-sig", "cp1250", "latin1"):
                try:
                    df = pd.read_csv(path, sep=";", engine="python", encoding=enc)
                    print(f"DEBUG INFRA ROZBUDOWA READ OK: {path} enc={enc} shape={getattr(df, 'shape', None)}")
                    return df
                except Exception as e:
                    last_err = e
                    continue
            print("DEBUG INFRA ROZBUDOWA READ FAIL:", path, "->", last_err)
            return None

        def _recalc_infra_costs():
            path_str = (self._infralog_path_var.get() or "").strip()
            # Brak ścieżki → po prostu pusto, bez popupów
            if not path_str:
                self._infracost_df = _pd.DataFrame()
                _render_infra_costs()
                return

            p = Path(path_str)
            # Plik nie istnieje → tylko wyczyść widok, żadnych komunikatów
            if not p.exists():
                print("DEBUG INFRA ROZBUDOWA: log file not found:", p)
                self._infracost_df = _pd.DataFrame()
                _render_infra_costs()
                return

            df_log = _read_infra_log(p)
            # Pusty / nieudany odczyt → traktujemy jak brak danych
            if df_log is None or getattr(df_log, "empty", True):
                print("DEBUG INFRA ROZBUDOWA: empty or unreadable log:", p)
                self._infracost_df = _pd.DataFrame()
                _render_infra_costs()
                return

            import pandas as pd
            df = df_log.copy()

            # wykryj podstawowe kolumny po nazwie (case-insensitive)
            colmap = {str(c).strip().lower(): c for c in df.columns}
            kraj_col = colmap.get("kraj")
            cena_col = None
            for key in ("cena", "koszt", "price", "cost"):
                if key in colmap:
                    cena_col = colmap[key]
                    break
            stan_col = None
            for key in ("stan", "tryb"):
                if key in colmap:
                    stan_col = colmap[key]
                    break

            if not (kraj_col and cena_col):
                print("DEBUG INFRA ROZBUDOWA: brak kolumn Kraj/Cena", list(df.columns))
                self._infracost_df = _pd.DataFrame()
                _render_infra_costs()
                return

            df[kraj_col] = df[kraj_col].astype(str).str.upper().str.strip()

            # Cena może być zapisana jako '300000', '300 000', '300,000' itd.
            df[cena_col] = (
                df[cena_col]
                .astype(str)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[cena_col] = pd.to_numeric(df[cena_col], errors="coerce").fillna(0.0)

            # bierzemy tylko wiersze „PO” (po rozbudowie)
            if stan_col:
                mask_po = df[stan_col].astype(str).str.upper().str.strip().eq("PO")
                df_use = df[mask_po].copy()
            else:
                df_use = df.copy()

            if df_use.empty:
                self._infracost_df = _pd.DataFrame()
                _render_infra_costs()
                return

            by_nat = df_use.groupby(kraj_col, as_index=False)[cena_col].sum()
            by_nat.columns = ["Kraj", "Suma"]
            by_nat = by_nat.sort_values("Suma", ascending=False).reset_index(drop=True)

            self._infracost_df = by_nat
            _render_infra_costs()

        # spróbuj policzyć na starcie (jeśli plik istnieje)
        try:
            _recalc_infra_costs()
        except Exception as e:
            print("DEBUG INFRA ROZBUDOWA RECALC ERR:", e)

        # NOWE: losowe spadki poziomów centrów
        tab_infra_drop = ttk.Frame(nb, name="infra_drop")
        nb.add(tab_infra_drop, text="Spadki centrów")
        self._build_infra_decay_tab(tab_infra_drop)

        # --- KOSZTY z "Kompleksy" (JEDNA zakładka, wiele widoków) ---
        self._flags_dir = Path(flags_dir) if flags_dir else None
        tab_costs = ttk.Frame(nb, name="koszty utrzymania skoczni")
        nb.add(tab_costs, text="Koszty utrzymania skoczni")

        # toolbar
        top_costs = ttk.Frame(tab_costs)
        top_costs.pack(fill="x", side="top")

        ttk.Label(top_costs, text="Widok:").pack(side="left", padx=(6,2), pady=6)

        view_var = tk.StringVar(value="Kraje — suma")
        view_cb = ttk.Combobox(top_costs, textvariable=view_var, state="readonly",
                               values=["Kraje — suma",
                                       "Kraje — rozbicie",
                                       "Kraje — suma + liczba",
                                       "Ranking",
                                       "Po klasie operacyjnej"])
        view_cb.pack(side="left", padx=(0,8), pady=6)

        ttk.Button(top_costs, text="Przelicz z pliku", command=lambda: _rebuild_costs()).pack(side="left", padx=6, pady=6)
        ttk.Button(top_costs, text="Eksportuj do CSV", command=_export_to_csv).pack(side="left", padx=6, pady=6)

        # kontener na tabelę
        table_wrap = ttk.Frame(tab_costs)
        table_wrap.pack(fill="both", expand=True)

        self._complexes_path = default_complexes
        _cache = {"df_src": None, "df_rows": None, "by_sum": None, "by_break": None, "by_count": None, "ranking": None}

        def _tree_simple(parent, df_data: pd.DataFrame, cols, stretch_last=False, with_flags=False):
            # wyczyść kontener
            for w in parent.winfo_children():
                w.destroy()

            container = ttk.Frame(parent); container.pack(fill="both", expand=True)
            yscroll = ttk.Scrollbar(container, orient="vertical")
            xscroll = ttk.Scrollbar(container, orient="horizontal")

            # jeśli chcemy flagi i pierwszą kolumną jest "Kraj" – użyj kolumny drzewa (#0)
            use_tree_col = with_flags and len(cols) > 0 and cols[0] == "Kraj"

            show_mode = "tree headings" if use_tree_col else "headings"
            tv = ttk.Treeview(
                container,
                columns=(cols if not use_tree_col else cols[1:]),
                show=show_mode,
                yscrollcommand=yscroll.set,
                xscrollcommand=xscroll.set,
                height=18
            )
            tv.img_refs = []  # żeby GC nie zjadł obrazków

            yscroll.config(command=tv.yview); xscroll.config(command=tv.xview)
            tv.grid(row=0, column=0, sticky="nsew")
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll.grid(row=1, column=0, sticky="ew")
            container.rowconfigure(0, weight=1); container.columnconfigure(0, weight=1)

            # nagłówki
            if use_tree_col:
                tv.heading("#0", text="Kraj")
                tv.column("#0", width=140, anchor="w")
                head_cols = cols[1:]
            else:
                head_cols = cols

            for c in head_cols:
                tv.heading(c, text=c)
                tv.column(c, width=120, anchor="center")
            if stretch_last and head_cols:
                tv.column(head_cols[-1], width=160, anchor="center")

            # dane
            if not df_data.empty:
                # upewnij się, że mamy te kolumny
                for c in cols:
                    if c not in df_data.columns:
                        df_data[c] = ""
                for _, row in df_data[cols].iterrows():
                    if use_tree_col:
                        code = str(row["Kraj"])
                        img = _get_flag_image(self._flags_dir, code)
                        vals = tuple("" if pd.isna(row.get(c, "")) else str(row.get(c, "")) for c in cols[1:])
                        kwargs = {"text": str(code), "values": vals}
                        if img is not None:
                            try:
                                _ = img.__str__  # minimalna weryfikacja, że to PhotoImage
                                kwargs["image"] = img
                            except Exception:
                                pass
                        tv.insert("", "end", **kwargs)
                        if img is not None:
                            tv.img_refs.append(img)
                    else:
                        tv.insert("", "end", values=[row[c] for c in cols])

            return tv

        def _compute_if_needed():
            if _cache["df_src"] is None:
                # było:
                # df_hills = getattr(self.hills_viewer, "_df", None)

                # ma być (sprytny fallback na wypadek starej wersji):
                try:
                    df_hills = getattr(self.hills_viewer, "df", None)
                    if df_hills is None:
                        df_hills = getattr(self.hills_viewer, "_df", None)
                except Exception:
                    df_hills = None

                df_src = build_complexes_from_hills(df_hills)
                df_rows, by_sum, by_break, by_count, ranking = compute_complex_costs(df_src)
                _cache.update(df_src=df_src, df_rows=df_rows, by_sum=by_sum, by_break=by_break, by_count=by_count, ranking=ranking)

        def _render_view():
            _compute_if_needed()
            mode = view_var.get()

            if mode == "Kraje — suma":
                df = _fmt_eur(_cache["by_sum"].copy(), ["Suma"])
                _tree_simple(table_wrap, df, cols=["Kraj","Suma"], stretch_last=True, with_flags=True)

            elif mode == "Kraje — rozbicie":
                pretty = _cache["by_break"].rename(columns={
                    "cost_seats":"Miejsca",
                    "cost_osw":"OS",
                    "cost_ig":"Ig",
                    "cost_kx":"Kx",
                    "cost_tw":"Tw",
                    "cost_kk":"Kk",
                    "cost_ks":"Ks",
                    "cost_poc":"Poc",
                    "cost_sia":"Sia",
                    "cost_nas":"Nas",
                }).copy()
                money_cols = [c for c in pretty.columns if c != "Kraj"]
                df = _fmt_eur(pretty, money_cols)
                cols = ["Kraj","Miejsca","OS","Ig","Kx","Tw","Kk","Ks","Poc","Sia","Nas","Suma"]
                _tree_simple(table_wrap, df, cols=cols, with_flags=True)

            elif mode == "Kraje — suma + liczba":
                df = _fmt_eur(_cache["by_count"].copy(), ["Suma"])
                _tree_simple(table_wrap, df, cols=["Kraj","Liczba obiektów","Suma"], with_flags=True)

            elif mode == "Ranking":
                df = _cache["ranking"].copy()
                df["Udział %"] = df["Udział %"].map(lambda x: f"{x:.2f}%")
                df = _fmt_eur(df, ["Suma"])
                _tree_simple(table_wrap, df, cols=["Kraj","Suma","Udział %"], stretch_last=True, with_flags=True)

            else:  # Po klasie operacyjnej
                df_rows_src = _cache["df_rows"]
                if df_rows_src is None or df_rows_src.empty:
                    return
                op_path = getattr(self, "_op_class_path", "")
                df_op = load_operational_classes(op_path)
                op_lookup: dict = {}
                if not df_op.empty and {"Kraj", "Miasto", "Klasa"}.issubset(df_op.columns):
                    for _, r in df_op.iterrows():
                        op_lookup[(str(r["Kraj"]).strip().upper(), str(r["Miasto"]).strip())] = str(r["Klasa"]).strip()
                rows_out = []
                for _, r in df_rows_src.iterrows():
                    nat = str(r.get("Kraj", "")).strip()
                    miasto = str(r.get("Miasto", "")).strip()
                    klasa = op_lookup.get((nat.upper(), miasto), "Pełna")
                    mult = _OP_MULTIPLIERS.get(klasa, 1.0)
                    full = float(r["Suma"])
                    eff = full * mult
                    sav = full - eff
                    rows_out.append({"Kraj": nat, "Miasto": miasto, "Klasa op.": klasa,
                                     "Pełny (€)": full, "Efektywny (€)": eff, "Oszczędność (€)": sav})
                df_view = pd.DataFrame(rows_out)
                df_view = _fmt_eur(df_view, ["Pełny (€)", "Efektywny (€)", "Oszczędność (€)"])
                cols_op = ["Kraj", "Miasto", "Klasa op.", "Pełny (€)", "Efektywny (€)", "Oszczędność (€)"]
                tv = _tree_simple(table_wrap, df_view, cols=cols_op, with_flags=True)
                tv.tag_configure("pol", foreground="#B8860B")
                tv.tag_configure("min", foreground="#CC0000")
                # with_flags + Kraj as #0 → values = (Miasto, Klasa op., ...)
                for iid in tv.get_children():
                    vals = tv.item(iid, "values")
                    if len(vals) >= 2:
                        klasa_val = vals[1]
                        if klasa_val == "Minimalna":
                            tv.item(iid, tags=("min",))
                        elif klasa_val == "Połowiczna":
                            tv.item(iid, tags=("pol",))

        def _rebuild_costs():
            # wymuś przeliczenie od zera i odśwież render
            _cache.update(df_src=None, df_rows=None, by_sum=None, by_break=None, by_count=None, ranking=None)
            _render_view()
            _render_complexes_tab()

        view_cb.bind("<<ComboboxSelected>>", lambda e: _render_view())
        _render_view()  # pierwszy render

        # auto-refresh „Kompleksy” na starcie
        _render_complexes_tab()

        # Klasa operacyjna skoczni
        self._op_class_path = "S51/Klasa operacyjna S51.csv"
        tab_op = ttk.Frame(nb, name="klasa_operacyjna")
        nb.add(tab_op, text="Klasa operacyjna")
        self._op_class_tab = OperationalClassTab(tab_op, hills_tab_ref=self)
        self._op_class_tab.pack(fill="both", expand=True)

        # Gdy HillBuilderTab wyśle sygnał odświeżenia, wywołaj metodę odświeżającą
        self.bind("<<HILLS_COMPLEXES_REFRESH>>", lambda e: self._handle_global_refresh())

    def _handle_global_refresh(self):
        """Wywoływane automatycznie przez sygnał z formularza."""
        # 1. Odśwież kompleksy
        self._render_complexes_tab()
        # 2. Przelicz koszty budowy i wyeksportuj do CSV
        self._recalc_build_costs()

    def _build_homologations_tab(self, parent):
        nb_sub = ttk.Notebook(parent)
        nb_sub.pack(fill="both", expand=True)

        # --- Zakładka 1: Wymagania (stary układ 2×2) ---
        tab_req = ttk.Frame(nb_sub)
        nb_sub.add(tab_req, text="Wymagania")

        root = ttk.Frame(tab_req)
        root.pack(fill="both", expand=True, padx=10, pady=10)
        for c in range(2):
            root.columnconfigure(c, weight=1)
        for r in range(2):
            root.rowconfigure(r, weight=1)

        classes = list(HOMOLOGATION_SPEC.items())
        for idx, (klass, spec) in enumerate(classes):
            row = idx // 2
            col = idx % 2
            box = ttk.Labelframe(root, text=klass)
            box.grid(row=row, column=col, sticky="nsew", padx=5, pady=5, ipadx=4, ipady=2)
            box.columnconfigure(1, weight=1)
            for r, (field, val) in enumerate(spec.items()):
                ttk.Label(box, text=field + ":", anchor="w").grid(row=r, column=0, sticky="w", padx=(8, 4), pady=1)
                ttk.Label(box, text=str(val), anchor="w").grid(row=r, column=1, sticky="w", padx=(0, 8), pady=1)

        # --- Zakładka 2: Sprawdzenie ---
        tab_check = ttk.Frame(nb_sub)
        nb_sub.add(tab_check, text="Sprawdzenie")

        bar = ttk.Frame(tab_check)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(bar, text="Plik skoczni:").pack(side="left")
        hills_var = getattr(self.hills_viewer, "var_path", tk.StringVar())
        ttk.Entry(bar, textvariable=hills_var, width=50).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(bar, text="Sprawdź", command=self._homo_check_refresh).pack(side="left", padx=4)
        ttk.Button(bar, text="Przypisz klasy i zapisz", command=self._homo_assign_classes).pack(side="left", padx=4)

        self._homo_summary_var = tk.StringVar(value="")
        ttk.Label(tab_check, textvariable=self._homo_summary_var, anchor="w").pack(
            fill="x", padx=8, pady=(0, 4)
        )

        cols = ("Repr.", "Kraj", "Miasto", "Skocznia", "Homologacja", "Najlepsza klasa", "Status", "Uwagi")
        frame_tv = ttk.Frame(tab_check)
        frame_tv.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        tv = ttk.Treeview(frame_tv, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            tv.heading(c, text=c)
        tv.column("Repr.",          width=100, stretch=False)
        tv.column("Kraj",           width=50,  stretch=False)
        tv.column("Miasto",         width=90,  stretch=False)
        tv.column("Skocznia",       width=150, stretch=False)
        tv.column("Homologacja",    width=150, stretch=False)
        tv.column("Najlepsza klasa",width=150, stretch=False)
        tv.column("Status",         width=110, stretch=False)
        tv.column("Uwagi",          width=300, stretch=True)

        tv.tag_configure("ok",      foreground="#005500", background="#e8f5e9")
        tv.tag_configure("fail",    foreground="#990000", background="#ffebee")
        tv.tag_configure("upgrade", foreground="#7a4100", background="#fff8e1")

        sb = ttk.Scrollbar(frame_tv, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._homo_tv = tv

    def _load_hills_for_homo(self) -> "pd.DataFrame":
        """Wczytuje CSV skoczni i zwraca DataFrame z normalizowanymi nagłówkami."""
        import pandas as _pd2
        path_str = getattr(self.hills_viewer, "var_path", tk.StringVar()).get().strip()
        if not path_str:
            return _pd2.DataFrame()
        p = Path(path_str)
        if not p.exists():
            return _pd2.DataFrame()
        df = None
        for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
            try:
                df = _pd2.read_csv(p, sep=";", dtype=str, encoding=enc)
                break
            except Exception:
                pass
        if df is None or df.empty:
            return _pd2.DataFrame()
        want = {
            "reprezentacja": "Reprezentacja", "kraj": "Kraj", "miasto": "Miasto",
            "skocznia": "Skocznia", "k": "K", "hs": "HS", "stan": "Stan",
            "homologacja": "Homologacja",
            "miejscadlakibicow": "Miejsca dla kibiców", "os": "OŚ", "ig": "Ig",
            "tw": "Tw", "kk": "Kk", "ks": "Ks", "poc": "Poc", "sia": "Sia", "nas": "Naś",
        }
        mapping = {}
        for c in list(df.columns):
            k = _canon_hdr(c)
            if k in want and want[k] not in mapping.values():
                mapping[c] = want[k]
            else:
                mapping[c] = c
        df = df.rename(columns=mapping)
        for col in want.values():
            if col not in df.columns:
                df[col] = ""
        return df

    def _homo_check_refresh(self):
        """Wypełnia treeview statusem homologacji dla każdej skoczni."""
        df = self._load_hills_for_homo()
        if df is None or df.empty:
            messagebox.showinfo("Info", "Brak danych skoczni. Sprawdź ścieżkę pliku.")
            return

        tv = self._homo_tv
        for item in tv.get_children():
            tv.delete(item)

        ok_count = fail_count = upgrade_count = 0

        for _, row in df.iterrows():
            declared = str(row.get("Homologacja", "") or "").strip().upper()
            best = _homo_best_class(row)

            d_idx = next((i for i, c in enumerate(_FIS_CLASS_ORDER) if c == declared), 99)
            b_idx = next((i for i, c in enumerate(_FIS_CLASS_ORDER) if c == best.upper()), 99)

            if b_idx < d_idx:
                status = "Możliwy awans"
                tag = "upgrade"
                uwagi = f"Kwalifikuje do: {best}"
                upgrade_count += 1
            elif b_idx > d_idx and d_idx < 99:
                missing = _homo_check_row(row, _FIS_CLASS_ORDER[d_idx])
                status = "Niezgodność"
                tag = "fail"
                uwagi = "; ".join(missing)
                fail_count += 1
            elif d_idx == 99 and b_idx == 99:
                status = "Brak klasy"
                tag = "fail"
                uwagi = "Nie spełnia żadnej klasy"
                fail_count += 1
            else:
                status = "OK"
                tag = "ok"
                uwagi = ""
                ok_count += 1

            tv.insert("", "end", values=(
                str(row.get("Reprezentacja", "")),
                str(row.get("Kraj", "")),
                str(row.get("Miasto", "")),
                str(row.get("Skocznia", "")),
                str(row.get("Homologacja", "")),
                best,
                status,
                uwagi,
            ), tags=(tag,))

        self._homo_summary_var.set(
            f"Wyniki:  OK: {ok_count}  |  Niezgodność: {fail_count}  |  Możliwy awans: {upgrade_count}"
        )

    def _homo_assign_classes(self):
        """Auto-przypisuje najlepszą klasę każdej skoczni i zapisuje do CSV."""
        df = self._load_hills_for_homo()
        if df is None or df.empty:
            messagebox.showinfo("Info", "Brak danych skoczni.")
            return

        changes = 0
        for idx, row in df.iterrows():
            best = _homo_best_class(row)
            old = str(row.get("Homologacja", "") or "").strip()
            if best != old:
                df.at[idx, "Homologacja"] = best
                changes += 1

        if changes == 0:
            messagebox.showinfo("Info", "Wszystkie klasy homologacji są już poprawne. Brak zmian.")
            return

        if not messagebox.askyesno("Potwierdź", f"Zostaną zmienione klasy dla {changes} skoczni. Zapisać?"):
            return

        path_str = getattr(self.hills_viewer, "var_path", tk.StringVar()).get().strip()
        p = Path(path_str)
        try:
            # Wczytaj oryginał, żeby zachować oryginalne kolumny
            orig_df = None
            for enc in ("utf-8-sig", "utf-8", "cp1250"):
                try:
                    orig_df = pd.read_csv(p, sep=";", dtype=str, encoding=enc)
                    break
                except Exception:
                    pass
            if orig_df is not None:
                homo_col_orig = next(
                    (c for c in orig_df.columns if _canon_hdr(c) == "homologacja"), None
                )
                if homo_col_orig:
                    orig_df[homo_col_orig] = df["Homologacja"].values
                    orig_df.to_csv(p, sep=";", index=False, encoding="cp1250")
                else:
                    df.to_csv(p, sep=";", index=False, encoding="cp1250")
            else:
                df.to_csv(p, sep=";", index=False, encoding="cp1250")

            messagebox.showinfo("OK", f"Zapisano. Zmieniono klasy dla {changes} skoczni.")
            self.hills_viewer.refresh()
            self._homo_check_refresh()
        except Exception as exc:
            messagebox.showerror("Błąd zapisu", str(exc))

    # --- Zakładka: inwestycje w centra infrastruktury (ME/EK/IN/ED) ---
    def _build_infra_upgrade_tab(self, parent):
        """Tabela z poziomami ME/EK/IN/ED: lewa kolumna = stan z pliku, prawa edytowalna.
        Ostatnia kolumna „Cena” liczy koszt awansu poziomów.
        Teraz w wersji na Canvas (jak 'Infrastruktura'), z możliwością edycji na podwójne kliknięcie.
        """
        import pandas as pd

        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        # korzystamy z tego samego patha co zakładka 'Infrastruktura'
        infra_var = self.infra_viewer.var_path if getattr(self, "infra_viewer", None) else tk.StringVar()

        ttk.Label(top, text="Plik infrastruktury:").pack(side="left")
        ttk.Entry(top, textvariable=infra_var, width=50).pack(side="left", padx=4, fill="x", expand=True)

        def _pick():
            p = filedialog.askopenfilename(
                title="Wybierz plik infrastruktury (CSV)",
                filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")]
            )
            if p:
                infra_var.set(p)
                if getattr(self, "infra_viewer", None) is not None:
                    self.infra_viewer.var_path.set(p)
                self._infra_upgrade_reload()

        ttk.Button(top, text="…", width=3, command=_pick).pack(side="left", padx=(0, 4))
        ttk.Button(top, text="Odśwież", command=self._infra_upgrade_reload).pack(side="left", padx=4)
        ttk.Button(top, text="Zapisz do infrastruktury", command=self._infra_upgrade_save).pack(side="right", padx=(4, 0))

        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._infra_upg_wrap = wrap

        # bufory robocze
        self._infra_upg_src = pd.DataFrame()
        self._infra_upg_df = pd.DataFrame()
        self._infra_center_cols = {}
        self._infra_upg_costs = {}

        # stan widoku Canvas
        self._infra_upg_canvas = None
        self._infra_upg_cols: list[str] = []
        self._infra_upg_row_index: list[int] = []
        self._infra_upg_header_h = 28
        self._infra_upg_row_h = 24

        # pierwszy render
        self._infra_upgrade_reload()

    def _build_infra_decay_tab(self, parent):
        """Zakładka: losowe spadki poziomów centrów infrastruktury (ME/EK/IN/ED)."""
        import pandas as pd
        import random
        from pathlib import Path
        from tkinter import messagebox

        # --- GÓRA: ścieżka pliku + przyciski ---
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=8, pady=(8, 4))

        # korzystamy z tego samego patha co zakładka 'Infrastruktura'
        infra_var = (
            self.infra_viewer.var_path
            if getattr(self, "infra_viewer", None) is not None
            else tk.StringVar()
        )

        ttk.Label(top, text="Plik infrastruktury:").pack(side="left")
        ttk.Entry(top, textvariable=infra_var, width=50).pack(
            side="left", padx=4, fill="x", expand=True
        )

        def _pick():
            p = filedialog.askopenfilename(
                title="Wybierz plik infrastruktury (CSV)",
                filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
            )
            if p:
                infra_var.set(p)
                if getattr(self, "infra_viewer", None) is not None:
                    self.infra_viewer.var_path.set(p)

        ttk.Button(top, text="…", width=3, command=_pick).pack(side="left", padx=(0, 4))

        ttk.Button(
            top, text="Losuj spadki", command=lambda: _do_random_drops()
        ).pack(side="left", padx=4)

        ttk.Button(
            top, text="Zapisz do infrastruktury", command=lambda: _save_drops()
        ).pack(side="right", padx=(4, 0))

        # --- DÓŁ: podgląd zmian ---
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._infradrop_wrap = wrap
        self._infradrop_df_full = pd.DataFrame()
        self._infradrop_changes = pd.DataFrame()

        # tekst z podsumowaniem
        self._infradrop_info = tk.StringVar(value="Brak wylosowanych spadków.")
        ttk.Label(parent, textvariable=self._infradrop_info).pack(
            fill="x", padx=8, pady=(0, 8)
        )

        def _tree_simple_build_local(parent, df_data: pd.DataFrame, cols, stretch_last=False, with_flags=False):
            # wyczyść kontener
            for w in parent.winfo_children():
                w.destroy()

            container = ttk.Frame(parent)
            container.pack(fill="both", expand=True)

            yscroll = ttk.Scrollbar(container, orient="vertical")
            xscroll = ttk.Scrollbar(container, orient="horizontal")

            use_tree_col = with_flags
            show_mode = "tree headings" if use_tree_col else "headings"

            tv = ttk.Treeview(
                container,
                columns=(cols if not use_tree_col else cols[1:]),
                show=show_mode,
                yscrollcommand=yscroll.set,
                xscrollcommand=xscroll.set,
                height=18,
            )
            tv.img_refs = []

            yscroll.config(command=tv.yview)
            xscroll.config(command=tv.xview)
            tv.grid(row=0, column=0, sticky="nsew")
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll.grid(row=1, column=0, sticky="ew")
            container.rowconfigure(0, weight=1)
            container.columnconfigure(0, weight=1)

            if use_tree_col:
                # w kolumnie drzewa pokażemy Reprezentację + flagę z kolumny Kraj
                tv.heading("#0", text="Reprezentacja")
                tv.column("#0", width=180, anchor="w")
                head_cols = cols[1:]
            else:
                head_cols = cols

            for c in head_cols:
                tv.heading(c, text=c)
                tv.column(c, width=120, anchor="center")
            if stretch_last and head_cols:
                tv.column(head_cols[-1], width=160, anchor="center")

            if df_data is None or df_data.empty:
                return tv

            # upewnij się, że kolumny istnieją
            for c in cols:
                if c not in df_data.columns:
                    df_data[c] = ""

            if use_tree_col:
                # z flagami w kolumnie drzewa
                for _, row in df_data[cols].iterrows():
                    nat = str(row.get("Kraj", "") or "")              # kod kraju do flagi
                    rep = str(row.get("Reprezentacja", "") or "")     # tekst w kolumnie drzewa

                    img = _get_flag_image(getattr(self, "_flags_dir", None), nat)

                    vals = tuple(
                        "" if pd.isna(row.get(c, "")) else str(row.get(c, ""))
                        for c in cols[1:]
                    )
                    kwargs = {"text": rep, "values": vals}
                    if img is not None:
                        kwargs["image"] = img
                        tv.img_refs.append(img)
                    tv.insert("", "end", **kwargs)
            else:
                # bez flag – zwykła tabelka
                for _, row in df_data[cols].iterrows():
                    vals = [
                        "" if pd.isna(row.get(c, "")) else str(row.get(c, ""))
                        for c in cols
                    ]
                    tv.insert("", "end", values=vals)

            return tv

        def _render_changes():
            df = self._infradrop_changes
            if not isinstance(df, pd.DataFrame) or df.empty:
                df = pd.DataFrame(
                    columns=["Reprezentacja", "Kraj", "Centrum", "Przed", "Po"]
                )

            _tree_simple_build_local(
                self._infradrop_wrap,
                df,
                cols=["Reprezentacja", "Kraj", "Centrum", "Przed", "Po"],
                stretch_last=True,
                with_flags=True,
            )


        def _load_infra_df():
            """Wczytuje plik infrastruktury tak samo jak viewer."""
            path_str = (infra_var.get() or "").strip()
            if not path_str:
                messagebox.showwarning(
                    "Spadki centrów", "Brak ścieżki do pliku infrastruktury."
                )
                return pd.DataFrame()

            p = Path(path_str)
            if not p.exists():
                messagebox.showwarning(
                    "Spadki centrów", f"Nie znaleziono pliku:\n{p}"
                )
                return pd.DataFrame()

            try:
                if getattr(self, "infra_viewer", None) is not None and hasattr(
                    self.infra_viewer, "_read_csv"
                ):
                    df = self.infra_viewer._read_csv(p)
                else:
                    df = pd.read_csv(p, sep=";", engine="python", encoding="cp1250")
            except Exception as e:
                messagebox.showerror(
                    "Spadki centrów", f"Nie udało się wczytać pliku infrastruktury:\n{e}"
                )
                return pd.DataFrame()

            return df

        def _do_random_drops():
            df = _load_infra_df()
            if not isinstance(df, pd.DataFrame) or df.empty:
                self._infradrop_df_full = pd.DataFrame()
                self._infradrop_changes = pd.DataFrame()
                self._infradrop_info.set("Brak danych w pliku infrastruktury.")
                _render_changes()
                return

            df = df.copy()

            # mapowanie ME/EK/IN/ED -> nazwy kolumn z poziomami
            center_cols = getattr(self, "_infra_center_cols", {}) or {}
            if not center_cols:
                # na wszelki wypadek, gdyby zakładka inwestycji nie była jeszcze renderowana
                try:
                    self._infra_upgrade_reload()
                    center_cols = getattr(self, "_infra_center_cols", {}) or {}
                except Exception:
                    center_cols = {}

            if not center_cols:
                messagebox.showwarning(
                    "Spadki centrów",
                    "Nie wykryto kolumn centrów ME/EK/IN/ED w infrastrukturze.",
                )
                self._infradrop_df_full = df
                self._infradrop_changes = pd.DataFrame()
                self._infradrop_info.set("Brak zidentyfikowanych centrów do obniżenia.")
                _render_changes()
                return

            # rozkład prawdopodobieństw per poziom
            prob = {
                1: 0.01,
                2: 0.03,
                3: 0.06,
                4: 0.10,
                5: 0.15,
            }

            cols = list(df.columns)

            # użyj dokładnie tego samego wykrywania, co w _infra_upgrade_reload
            nat_col = next(
                (c for c in cols if str(c).strip().lower() in {"kraj", "nat", "code", "kod"}),
                None,
            )
            name_col = next(
                (c for c in cols if str(c).strip().lower() in {"reprezentacja", "nation", "country", "country name"}),
                None,
            )

            rep_col = name_col or nat_col
            country_col = nat_col if nat_col != rep_col else None

            changes = []

            # Pandas 2.x nie pozwala wpisać str do kolumny int64 –
            # kolumny centrów trzymają mieszane wartości ("-" i liczby),
            # więc konwertujemy je do object przed modyfikacją.
            for col in center_cols.values():
                if col in df.columns and df[col].dtype != object:
                    df[col] = df[col].astype(object)

            for idx in df.index:
                row = df.loc[idx]

                # nazwa reprezentacji (to, co pokazujesz jako "Reprezentacja")
                rep = ""
                if rep_col:
                    rep = str(row.get(rep_col, "") or "")
                if not rep and country_col:
                    rep = str(row.get(country_col, "") or "")

                # kod kraju do kolumny "Kraj" + do flag
                if country_col:
                    nat = str(row.get(country_col, "") or "")
                else:
                    nat = str(row.get(rep_col, "") or "")

                for tag, col in center_cols.items():
                    if col not in df.columns:
                        continue

                    old_val = df.at[idx, col]
                    old_lvl = self._infra_upgrade_level(old_val)
                    if old_lvl <= 0:
                        continue

                    p = prob.get(old_lvl, 0.0)
                    if p <= 0:
                        continue

                    if random.random() < p:
                        new_lvl = old_lvl - 1
                        if new_lvl <= 0:
                            new_val = "-"
                        else:
                            new_val = str(new_lvl)

                        df.at[idx, col] = new_val

                        changes.append(
                            {
                                "Reprezentacja": rep,
                                "Kraj": nat,
                                "Centrum": tag,
                                "Przed": str(old_lvl),
                                "Po": "-" if new_lvl <= 0 else str(new_lvl),
                            }
                        )

            self._infradrop_df_full = df
            self._infradrop_changes = pd.DataFrame(changes)

            if not changes:
                self._infradrop_info.set("W tym losowaniu żadne centrum nie spadło.")
            else:
                # proste podsumowanie
                total = len(changes)
                by_tag = {}
                for ch in changes:
                    by_tag[ch["Centrum"]] = by_tag.get(ch["Centrum"], 0) + 1
                parts = [f"{k}: {v}" for k, v in sorted(by_tag.items())]
                self._infradrop_info.set(
                    f"Spadki: {total} centrów ({', '.join(parts)})."
                )

            _render_changes()

        def _save_drops():
            df = getattr(self, "_infradrop_df_full", None)
            if not isinstance(df, pd.DataFrame) or df.empty:
                messagebox.showwarning(
                    "Spadki centrów",
                    "Brak wylosowanych zmian do zapisania. Najpierw użyj 'Losuj spadki'.",
                )
                return

            path_str = (infra_var.get() or "").strip()
            if not path_str:
                messagebox.showwarning(
                    "Spadki centrów", "Brak ścieżki do pliku infrastruktury."
                )
                return

            p = Path(path_str)
            try:
                df.to_csv(p, sep=";", encoding="cp1250", index=False)
            except Exception as e:
                messagebox.showerror(
                    "Spadki centrów", f"Nie udało się zapisać pliku:\n{e}"
                )
                return

            # spróbuj odświeżyć inne widoki, żeby były spójne
            try:
                if getattr(self, "infra_viewer", None) is not None:
                    # jeżeli viewer ma jakiś reload/odśwież – często tak nazywałeś
                    if hasattr(self.infra_viewer, "reload"):
                        self.infra_viewer.reload()
                    elif hasattr(self.infra_viewer, "_reload"):
                        self.infra_viewer._reload()
            except Exception:
                pass

            try:
                # przeładuj też zakładkę „Inwestycje w centra”
                self._infra_upgrade_reload()
            except Exception:
                pass

            messagebox.showinfo(
                "Spadki centrów", f"Zapisano zmiany do pliku:\n{p}"
            )

        # pierwszy pusty render
        _render_changes()

    def _infra_upgrade_norm_val(self, val):
        s = str(val).strip()
        if s in ("", "-", "–", "—", "0"):
            return "-"
        try:
            n = int(float(s))
        except Exception:
            return "-"
        if n <= 0:
            return "-"
        return str(max(1, min(5, n)))

    def _infra_upgrade_level(self, val):
        s = str(val).strip()
        if s in ("", "-", "–", "—"):
            return 0
        try:
            n = int(float(s))
        except Exception:
            return 0
        return max(0, min(5, n))

    def _infra_upgrade_step_cost(self, from_level: int, to_level: int) -> int:
        # koszty za każdy „skok” poziomu
        STEP = {
            0: 150_000,  # '-'/0 -> 1
            1: 200_000,  # 1 -> 2
            2: 300_000,  # 2 -> 3
            3: 400_000,  # 3 -> 4
            4: 500_000,  # 4 -> 5
        }
        cost = 0
        x = int(from_level)
        to_level = int(to_level)
        while x < to_level:
            cost += STEP.get(x, 0)
            x += 1
        return cost

    def _infra_upgrade_fmt_eur(self, amount: int) -> str:
        if not amount or amount <= 0:
            return "0 €"
        s = f"{int(amount):,}".replace(",", " ")
        return f"{s} €"

    def _infra_upgrade_reload(self):
        import pandas as pd
        from pathlib import Path

        wrap = getattr(self, "_infra_upg_wrap", None)
        if wrap is None:
            return

        # wyczyść widok
        for w in wrap.winfo_children():
            w.destroy()

        # ścieżka pliku infrastruktury – bierzemy z istniejącej zakładki "Infrastruktura"
        path_str = ""
        if getattr(self, "infra_viewer", None) is not None:
            path_str = self.infra_viewer.var_path.get().strip()
        path = Path(path_str) if path_str else None

        # wczytanie CSV tak samo jak w viewerze infrastruktury
        try:
            if path and hasattr(self.infra_viewer, "_read_csv"):
                df = self.infra_viewer._read_csv(path)
            else:
                df = pd.DataFrame()
        except Exception:
            df = pd.DataFrame()

        if not isinstance(df, pd.DataFrame) or df.empty:
            ttk.Label(wrap, text="Brak danych w pliku infrastruktury.").pack(padx=8, pady=8)
            self._infra_upg_src = pd.DataFrame()
            self._infra_upg_df = pd.DataFrame()
            self._infra_center_cols = {}
            self._infra_upg_costs = {}
            self._infra_upg_cols = []
            self._infra_upg_row_index = []
            self._infra_upg_canvas = None
            return

        df = df.copy()
        self._infra_upg_src = df.copy()
        self._infra_upg_df = df.copy()

        cols = list(df.columns)

        # wykryj kolumny: "Reprezentacja" i "Kraj"/"NAT" itp.
        nat_col = next(
            (c for c in cols if str(c).strip().lower() in {"kraj", "nat", "code", "kod"}),
            None,
        )
        name_col = next(
            (c for c in cols if str(c).strip().lower() in {"reprezentacja", "nation", "country", "country name"}),
            None,
        )

        # co traktujemy jako nazwę reprezentacji, a co jako kraj do flagi
        rep_col = name_col or nat_col
        country_col = nat_col if nat_col != rep_col else None

        # --- mapowanie ME/EK/IN/ED/ZY na konkretne kolumny z pliku ---
        keys = ["ME", "EK", "IN", "ED", "ZY"]
        name_map = {
            "ME": "CENTRUM MEDYCZNE",
            "EK": "CENTRUM EKONOMICZNE",
            "IN": "CENTRUM INŻYNIERYJNE",
            "ED": "CENTRUM EDUKACYJNE",
            "ZY": "CENTRUM ŻYWIENIOWE",
        }

        center_cols: dict[str, str] = {}

        # 1) szukamy dokładnie po nazwie
        up_cols = [str(c).strip().upper() for c in cols]
        for key in keys:
            pretty = name_map[key]
            col = next(
                (c for c, upc in zip(cols, up_cols) if upc == pretty),
                None,
            )
            if col:
                center_cols[key] = col

        # 2) awaryjnie: użyj kolumn skalowych z viewer'a infrastruktury, jeśli takie są
        if not center_cols and getattr(self, "infra_viewer", None) is not None:
            scale_cols = list(getattr(self.infra_viewer, "scale_cols", []))
            for key, col in zip(keys, scale_cols):
                if col in cols:
                    center_cols[key] = col

        self._infra_center_cols = center_cols

        # kolejność kolumn na Canvasie:
        # Reprezentacja (z flagą), Kraj, ME/EK/IN/ED (old/new), Cena
        grid_cols: list[str] = []

        # zawsze pokazujemy "Reprezentacja" (tekst + flaga jeśli się da)
        grid_cols.append("Reprezentacja")

        # osobna kolumna "Kraj", jeśli w ogóle mamy skąd brać
        if country_col is not None:
            grid_cols.append("Kraj")

        for key in keys:
            if key in center_cols:
                grid_cols.append(f"{key}_old")
                grid_cols.append(f"{key}_new")

        grid_cols.append("Cena")

        self._infra_upg_cols = grid_cols
        self._infra_upg_row_index = list(df.index)

        # zapamiętaj, z których kolumn bierzemy dane
        self._infra_upg_rep_col = rep_col
        self._infra_upg_country_col = country_col

        # policz koszt dla wszystkich wierszy
        self._infra_upg_costs = {}
        for idx in self._infra_upg_row_index:
            self._infra_upg_costs[idx] = self._infra_upgrade_calc_cost(idx)

        # Canvas + scroll
        canvas = tk.Canvas(wrap, background="white", highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self._infra_upg_canvas = canvas

        canvas.bind("<Double-1>", self._infra_upgrade_on_dblclick)
        canvas.bind("<Enter>", lambda e: self._infra_upg_mousewheel_bind(True))
        canvas.bind("<Leave>", lambda e: self._infra_upg_mousewheel_bind(False))

        self._infra_upgrade_redraw_canvas()

    def _infra_upgrade_calc_cost(self, idx: int) -> int:
        """Policz koszt zwiększenia poziomów centrów dla danego wiersza."""
        if idx not in self._infra_upg_src.index or idx not in self._infra_upg_df.index:
            return 0

        src = self._infra_upg_src.loc[idx]
        new = self._infra_upg_df.loc[idx]

        total = 0
        for key, col in self._infra_center_cols.items():
            old_val = src.get(col, "")
            new_val = new.get(col, "")
            lo = self._infra_upgrade_level(old_val)
            ln = self._infra_upgrade_level(new_val)
            if ln > lo:
                total += self._infra_upgrade_step_cost(lo, ln)

        return int(total)

    def _infra_upgrade_redraw_canvas(self):
        """Rysuje całą siatkę na Canvasie."""
        canvas = self._infra_upg_canvas
        if canvas is None:
            return

        canvas.delete("all")

        cols = list(self._infra_upg_cols)
        idx_list = list(self._infra_upg_row_index)
        if not cols or not idx_list:
            canvas.configure(scrollregion=(0, 0, 0, 0))
            return

        header_h = self._infra_upg_header_h
        row_h = self._infra_upg_row_h

        # szerokości kolumn
        widths: dict[str, int] = {}
        for c in cols:
            if c == "Reprezentacja":
                widths[c] = 200
            elif c == "Kraj":
                widths[c] = 80
            elif c == "Cena":
                widths[c] = 110
            elif c.endswith("_old") or c.endswith("_new"):
                widths[c] = 50
            else:
                widths[c] = 90

        # nagłówki
        x = 0
        fnt_head = tkfont.nametofont("TkHeadingFont") if hasattr(tkfont, "nametofont") else None
        for c in cols:
            if c == "Reprezentacja":
                txt = "Reprezentacja"
            elif c == "Kraj":
                txt = "Kraj"
            elif c == "Cena":
                txt = "Cena"
            elif c.endswith("_old"):
                txt = f"{c.split('_')[0]} (ob)"
            elif c.endswith("_new"):
                txt = f"{c.split('_')[0]} (po)"
            else:
                txt = c

            canvas.create_rectangle(x, 0, x + widths[c], header_h, fill="#ddd", outline="#999")
            canvas.create_text(
                x + widths[c] / 2,
                header_h / 2,
                text=txt,
                anchor="center",
                font=fnt_head,
            )
            x += widths[c]

        flags_dir = getattr(self.infra_viewer, "flags_dir", None) if getattr(self, "infra_viewer", None) is not None else None

        y = header_h
        for idx in idx_list:
            row = self._infra_upg_df.loc[idx]
            src = self._infra_upg_src.loc[idx]
            x = 0
            for c in cols:
                bg = "#ffffff"
                val = ""
                anchor = "center"

                if c == "Reprezentacja":
                    name = str(row.get(self._infra_upg_rep_col, "") if getattr(self, "_infra_upg_rep_col", None) else "")
                    nat = str(row.get(self._infra_upg_country_col, "") if getattr(self, "_infra_upg_country_col", None) else "")
                    val = name
                    anchor = "w"
                elif c == "Kraj":
                    val = str(row.get(self._infra_upg_country_col, "") if getattr(self, "_infra_upg_country_col", None) else "")
                    anchor = "w"
                elif c == "Cena":
                    cost = self._infra_upg_costs.get(idx, 0)
                    val = self._infra_upgrade_fmt_eur(cost)
                elif c.endswith("_old") or c.endswith("_new"):
                    key = c.split("_")[0]
                    colname = self._infra_center_cols.get(key)
                    base_series = src if c.endswith("_old") else row
                    raw_v = base_series.get(colname, "") if colname else ""
                    norm = self._infra_upgrade_norm_val(raw_v)
                    val = norm
                    lvl = self._infra_upgrade_level(norm)
                    lvl = max(0, min(5, lvl))
                    palette = getattr(InfraCanvasGrid, "PALETTE", None)
                    if palette and lvl in palette:
                        bg = palette[lvl]

                # prostokąt komórki
                canvas.create_rectangle(x, y, x + widths[c], y + row_h, fill=bg, outline="#cccccc")

                # tekst / flaga
                if c == "Reprezentacja":
                    name = val
                    nat = str(row.get(self._infra_upg_country_col, "") if getattr(self, "_infra_upg_country_col", None) else "")
                    draw_x = x + 6

                    if flags_dir and nat:
                        img = _get_flag_image(flags_dir, nat)
                        if img:
                            canvas.create_image(draw_x, y + row_h / 2, image=img, anchor="w")
                            draw_x += img.width() + 4

                    canvas.create_text(
                        draw_x,
                        y + row_h / 2,
                        text=str(name),
                        anchor="w",
                    )
                else:
                    canvas.create_text(
                        x + (widths[c] / 2 if anchor == "center" else 6),
                        y + row_h / 2,
                        text=str(val),
                        anchor=anchor,
                    )

                x += widths[c]
            y += row_h

        total_w = sum(widths.values())
        canvas.configure(scrollregion=(0, 0, total_w, y))

    def _infra_upg_mousewheel_bind(self, enable: bool):
        """Obsługa podpięcia kółka myszy dla Canvas w zakładce Centra."""
        canvas = self._infra_upg_canvas
        if canvas is None:
            return

        if enable:
            canvas.focus_set()
            canvas.bind_all("<MouseWheel>", self._infra_upg_on_mousewheel, add="+")
            canvas.bind_all("<Shift-MouseWheel>", self._infra_upg_on_shift_mousewheel, add="+")
            canvas.bind_all("<Button-4>", self._infra_upg_on_linux_wheel_up, add="+")
            canvas.bind_all("<Button-5>", self._infra_upg_on_linux_wheel_down, add="+")
        else:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Shift-MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

    def _infra_upg_on_mousewheel(self, event):
        canvas = self._infra_upg_canvas
        if canvas is None:
            return
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            canvas.yview_scroll(delta, "units")

    def _infra_upg_on_shift_mousewheel(self, event):
        canvas = self._infra_upg_canvas
        if canvas is None:
            return
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            canvas.xview_scroll(delta, "units")

    def _infra_upg_on_linux_wheel_up(self, event):
        canvas = self._infra_upg_canvas
        if canvas is None:
            return
        canvas.yview_scroll(-1, "units")

    def _infra_upg_on_linux_wheel_down(self, event):
        canvas = self._infra_upg_canvas
        if canvas is None:
            return
        canvas.yview_scroll(1, "units")

    def _infra_upgrade_on_dblclick(self, event):
        """Edycja pola *_new na Canvasie (Spinbox 1–5)."""
        canvas = self._infra_upg_canvas
        if canvas is None:
            return

        if not self._infra_upg_cols or not self._infra_upg_row_index:
            return

        header_h = self._infra_upg_header_h
        row_h = self._infra_upg_row_h

        # współrzędne w układzie canvas (uwzględniają scroll)
        y_canvas = canvas.canvasy(event.y)
        x_canvas = canvas.canvasx(event.x)

        # kliknięcie w nagłówek nas nie interesuje
        if y_canvas < header_h:
            return

        # który wiersz?
        row_idx_in_view = int((y_canvas - header_h) // row_h)
        if row_idx_in_view < 0 or row_idx_in_view >= len(self._infra_upg_row_index):
            return

        # która kolumna?
        cols = list(self._infra_upg_cols)
        widths = []
        for c in cols:
            if c == "Reprezentacja":
                widths.append(200)
            elif c == "Kraj":
                widths.append(80)
            elif c == "Cena":
                widths.append(110)
            elif c.endswith("_old") or c.endswith("_new"):
                widths.append(50)
            else:
                widths.append(90)

        x_world = 0
        col_index = -1
        for i, w in enumerate(widths):
            if x_world <= x_canvas < x_world + w:
                col_index = i
                break
            x_world += w

        if col_index < 0 or col_index >= len(cols):
            return

        col_name = cols[col_index]
        if not col_name.endswith("_new"):
            return

        # współrzędne komórki w "świecie" canvas
        cell_x1 = sum(widths[:col_index])
        cell_x2 = cell_x1 + widths[col_index]
        cell_y1 = header_h + row_idx_in_view * row_h
        cell_y2 = cell_y1 + row_h

        idx = self._infra_upg_row_index[row_idx_in_view]
        key = col_name.split("_")[0]
        col_in_df = self._infra_center_cols.get(key)

        if not col_in_df or idx not in self._infra_upg_df.index:
            return

        current_raw = self._infra_upg_df.at[idx, col_in_df]
        current_norm = self._infra_upgrade_norm_val(current_raw)

        spin = ttk.Spinbox(canvas, from_=1, to=5, increment=1, width=4, justify="center")
        spin.delete(0, "end")
        if current_norm and current_norm not in ("-", "0"):
            spin.insert(0, current_norm)
        else:
            spin.insert(0, "1")

        # przeliczenie współrzędnych komórki na układ widocznej części canvas
        view_x0 = canvas.canvasx(0)
        view_y0 = canvas.canvasy(0)
        x_place = cell_x1 - view_x0 + 2
        y_place = cell_y1 - view_y0 + 2

        spin.place(
            x=x_place,
            y=y_place,
            width=(cell_x2 - cell_x1) - 4,
            height=(cell_y2 - cell_y1) - 4,
        )
        spin.focus_set()

        def _commit(event=None):
            try:
                v = spin.get().strip()
            finally:
                spin.destroy()

            if v in ("", "-", "0"):
                disp = "-"
            else:
                try:
                    n = int(v)
                except Exception:
                    n = 1
                n = max(1, min(5, n))
                disp = str(n)

            # przygotuj wartość do zapisania w DF
            if disp == "-":
                new_val = ""
            else:
                new_val = disp  # trzymamy jako string, nie int

            # upewnij się, że kolumna jest typu object, żeby nie było konfliktu z int64
            try:
                if col_in_df in self._infra_upg_df.columns:
                    self._infra_upg_df[col_in_df] = self._infra_upg_df[col_in_df].astype("object")
            except Exception:
                pass

            self._infra_upg_df.at[idx, col_in_df] = new_val

            # przelicz koszt i odśwież rysunek
            self._infra_upg_costs[idx] = self._infra_upgrade_calc_cost(idx)
            self._infra_upgrade_redraw_canvas()

        spin.bind("<Return>", _commit)
        spin.bind("<KP_Enter>", _commit)
        def _cancel(event=None):
            spin.destroy()

        spin.bind("<Escape>", _cancel)

    def _infra_upgrade_append_log(self, infra_path):
        """
        Dopisuje do 'Rozbudowa Infrastruktury S51.csv' snapshot PRZED/PO + cena
        tylko dla wierszy, w których podniesiono poziom któregoś z centrów.
        """
        import pandas as pd
        from pathlib import Path
        from datetime import datetime
        import csv

        df_old = getattr(self, "_infra_upg_src", None)
        df_new = getattr(self, "_infra_upg_df", None)
        center_cols = getattr(self, "_infra_center_cols", None)

        if df_old is None or df_new is None or df_old.empty or df_new.empty or not center_cols:
            return

        # indeksy które realnie mamy w obu DataFrame'ach
        idx_list = list(getattr(self, "_infra_upg_row_index", [])) or list(df_new.index)

        # plik logu obok pliku infrastruktury
        infra_path = Path(infra_path)
        out_path = infra_path.with_name("Rozbudowa Infrastruktury S51.csv")

        LOG_HEADERS = ["TS", "Reprezentacja", "Kraj", "Stan", "ME", "EK", "IN", "ED", "ZY", "Cena"]
        new_file = not out_path.exists() or out_path.stat().st_size == 0
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rep_col = getattr(self, "_infra_upg_rep_col", None)
        nat_col = getattr(self, "_infra_upg_country_col", None)

        rows = []

        for idx in idx_list:
            if idx not in df_old.index or idx not in df_new.index:
                continue

            src = df_old.loc[idx]
            row = df_new.loc[idx]

            # policz poziomy PRZED/PO dla każdego centrum
            levels_old = {}
            levels_new = {}
            changed = False
            for key, col in center_cols.items():
                old_val = src.get(col, "")
                new_val = row.get(col, "")
                lo = self._infra_upgrade_level(old_val)
                ln = self._infra_upgrade_level(new_val)
                levels_old[key] = lo
                levels_new[key] = ln
                if ln > lo:
                    changed = True

            # jeśli nic nie podnieśliśmy, nic nie logujemy
            if not changed:
                continue

            rep = str(src.get(rep_col, "")) if rep_col else ""
            nat = str(src.get(nat_col, "")) if nat_col else ""

            cost = int(getattr(self, "_infra_upg_costs", {}).get(idx, 0) or 0)

            # snapshot PRZED
            rows.append([
                ts,
                rep,
                nat,
                "PRZED",
                levels_old.get("ME", 0),
                levels_old.get("EK", 0),
                levels_old.get("IN", 0),
                levels_old.get("ED", 0),
                levels_old.get("ZY", 0),
                0,          # cena tylko w wierszu PO
            ])

            # snapshot PO
            rows.append([
                ts,
                rep,
                nat,
                "PO",
                levels_new.get("ME", 0),
                levels_new.get("EK", 0),
                levels_new.get("IN", 0),
                levels_new.get("ED", 0),
                levels_new.get("ZY", 0),
                cost,
            ])

        if not rows:
            return

        # dopisz do CSV
        with open(out_path, "a", encoding="cp1250", newline="") as f:
            w = csv.writer(f, delimiter=";")
            if new_file:
                w.writerow(LOG_HEADERS)
            w.writerows(rows)

    def _infra_upgrade_save(self):
        from pathlib import Path
        from tkinter import messagebox

        df_new = getattr(self, "_infra_upg_df", None)
        if df_new is None or df_new.empty:
            messagebox.showwarning("Infrastruktura", "Brak danych do zapisania.")
            return

        path_str = ""
        if getattr(self, "infra_viewer", None) is not None:
            path_str = self.infra_viewer.var_path.get().strip()
        if not path_str:
            messagebox.showwarning("Infrastruktura", "Brak ścieżki do pliku infrastruktury.")
            return

        path = Path(path_str)

        # 1) Spróbuj dopisać log PRZED/PO + cena do Rozbudowa Infrastruktury S51.csv
        try:
            self._infra_upgrade_append_log(path)
        except Exception as e:
            # nie wywalaj zapisu infrastruktury jeśli log padnie
            messagebox.showwarning(
                "Infrastruktura",
                f"Zapis infrastruktury OK, ale nie udało się dopisać logu do 'Rozbudowa Infrastruktury S51.csv':\n{e}"
            )

        # 2) Zapisz zaktualizowany plik infrastruktury
        try:
            df_new.to_csv(path, sep=";", encoding="cp1250", index=False)
        except Exception as e:
            messagebox.showerror("Infrastruktura", f"Nie udało się zapisać pliku:\n{e}")
            return

        # 3) Zaktualizuj „stan przed” na potrzeby kolejnych zmian
        try:
            import pandas as pd
            self._infra_upg_src = df_new.copy()
            # przelicz koszty od zera, bo nowe „PRZED” = obecny stan
            self._infra_upg_costs = {}
            for idx in getattr(self, "_infra_upg_row_index", []):
                if idx in self._infra_upg_src.index:
                    self._infra_upg_costs[idx] = self._infra_upgrade_calc_cost(idx)
            self._infra_upgrade_redraw_canvas()
        except Exception:
            pass

        messagebox.showinfo("Infrastruktura", f"Zapisano zmiany do pliku:\n{path}")


_CLASS_RANK = {"Pełna": 0, "Połowiczna": 1, "Minimalna": 2}


class _DowngradeDialog(tk.Toplevel):
    """Dialog z checkboxami do wyboru, które obniżenia klasy operacyjnej zatwierdzić."""

    def __init__(self, parent, downgrades: list):
        """
        downgrades: list of (kraj, miasto, cur_cls, new_cls)
        Po zamknięciu: self.approved – set of (kraj, miasto) gdzie obniżenie zatwierdzone,
                       self.cancelled – True jeśli użytkownik anulował.
        """
        super().__init__(parent)
        self.title("Planowane obniżenia klasy operacyjnej")
        self.resizable(True, True)
        self.approved: set = set()
        self.cancelled: bool = True
        self._vars: dict = {}

        ttk.Label(
            self,
            text="Odznacz skocznie, których klasy NIE chcesz obniżać:",
            font=("TkDefaultFont", 9, "bold")
        ).pack(padx=12, pady=(10, 4), anchor="w")

        # Scrollowalna lista
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=12)
        canvas = tk.Canvas(outer, height=min(400, max(120, len(downgrades) * 26 + 20)),
                           highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        # Nagłówek
        hdr = ttk.Frame(inner)
        hdr.pack(fill="x", pady=(0, 2))
        ttk.Label(hdr, text="Kraj", width=7, anchor="w").pack(side="left")
        ttk.Label(hdr, text="Miasto", width=18, anchor="w").pack(side="left")
        ttk.Label(hdr, text="Zmiana klasy", width=30, anchor="w").pack(side="left")
        ttk.Label(hdr, text="Obniż?", width=8, anchor="center").pack(side="left")
        ttk.Separator(inner, orient="horizontal").pack(fill="x")

        for kraj, miasto, cur_cls, new_cls in sorted(downgrades, key=lambda x: (x[0], x[1])):
            var = tk.BooleanVar(value=True)   # domyślnie: zatwierdź obniżenie
            self._vars[(kraj, miasto)] = var
            row = ttk.Frame(inner)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=kraj, width=7, anchor="w").pack(side="left")
            ttk.Label(row, text=miasto, width=18, anchor="w").pack(side="left")
            ttk.Label(row, text=f"{cur_cls}  →  {new_cls}", width=30, anchor="w").pack(side="left")
            ttk.Checkbutton(row, variable=var).pack(side="left")

        # Przyciski
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=12, pady=(4, 0))
        btn_bar = ttk.Frame(self)
        btn_bar.pack(fill="x", padx=12, pady=8)
        ttk.Button(btn_bar, text="Zaznacz wszystkie",
                   command=lambda: [v.set(True)  for v in self._vars.values()]).pack(side="left")
        ttk.Button(btn_bar, text="Odznacz wszystkie",
                   command=lambda: [v.set(False) for v in self._vars.values()]).pack(side="left", padx=4)
        ttk.Button(btn_bar, text="Anuluj", command=self._cancel).pack(side="right")
        ttk.Button(btn_bar, text="Zastosuj", command=self._apply).pack(side="right", padx=4)

        self.transient(parent)
        self.grab_set()
        self.update_idletasks()
        self.minsize(500, 200)

    def _apply(self):
        self.approved = {k for k, v in self._vars.items() if v.get()}
        self.cancelled = False
        self.destroy()

    def _cancel(self):
        self.cancelled = True
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
class OperationalClassTab(ttk.Frame):
    """Zakładka: Klasa operacyjna skoczni (wybór per kompleks + degradacja)."""

    def __init__(self, parent, hills_tab_ref):
        super().__init__(parent)
        self._ht = hills_tab_ref
        self._data: dict = {}         # (Kraj, Miasto) → {"Klasa": str, "Sezony_POL": int, "Sezony_MIN": int}
        self._full_costs: dict = {}   # (Kraj, Miasto) → int
        self._fis_classes: dict = {}  # (Kraj, Miasto) → str
        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Pasek ścieżki
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(top, text="Plik klasy operacyjnej:").pack(side="left")
        self._path_var = tk.StringVar(value="S51/Klasa operacyjna S51.csv")
        ttk.Entry(top, textvariable=self._path_var, width=42).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(top, text="Wybierz…", command=self._pick_file).pack(side="left")
        ttk.Button(top, text="Załaduj", command=self.refresh).pack(side="left", padx=(4, 0))

        # Pasek akcji
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=4)
        ttk.Label(bar, text="Ustaw zaznaczone na:").pack(side="left")
        self._bulk_cb = ttk.Combobox(bar, values=_OP_CHOICES, state="readonly", width=11)
        self._bulk_cb.set("Pełna")
        self._bulk_cb.pack(side="left", padx=4)
        ttk.Button(bar, text="Zastosuj", command=self._bulk_apply).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text="Przelicz", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Auto z klasyfikacji", command=self._auto_op_classes).pack(side="left", padx=4)
        ttk.Button(bar, text="Zapisz", command=self._save).pack(side="left", padx=4)
        ttk.Button(bar, text="Zakończ sezon →", command=self._season_end).pack(side="left", padx=(8, 0))

        # Tabela
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        cols = ["Miasto", "Klasa FIS", "Klasa eff.", "Klasa op.", "Sez. POL", "Sez. MIN", "Koszt pełny €", "Koszt efektywny €"]
        self._tv = ttk.Treeview(wrap, columns=cols, show="tree headings", height=16, selectmode="extended")
        vsb = ttk.Scrollbar(wrap, orient="vertical",   command=self._tv.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self._tv.xview)
        self._tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self._tv.heading("#0", text="Kraj")
        self._tv.column("#0", width=100, anchor="w")
        widths = {"Miasto": 120, "Klasa FIS": 175, "Klasa eff.": 175, "Klasa op.": 95,
                  "Sez. POL": 65, "Sez. MIN": 65, "Koszt pełny €": 120, "Koszt efektywny €": 130}
        for c in cols:
            self._tv.heading(c, text=c)
            self._tv.column(c, width=widths.get(c, 100), anchor="center")

        self._tv.tag_configure("min", foreground="#cc3300")
        self._tv.tag_configure("pol", foreground="#886600")
        self._tv.tag_configure("warn", background="#fff3cd")  # żółte ostrzeżenie (zbliżenie do progu degradacji)

        # Podsumowanie
        self._summary_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._summary_var, anchor="w",
                  font=("TkDefaultFont", 9)).pack(fill="x", padx=8, pady=(0, 8))

        self.refresh()

    # ── Dane ─────────────────────────────────────────────────────────────────

    def _get_complexes(self) -> pd.DataFrame:
        try:
            df_h = getattr(self._ht.hills_viewer, "df", None)
            if df_h is None:
                df_h = getattr(self._ht.hills_viewer, "_df", None)
            return build_complexes_from_hills(df_h)
        except Exception:
            return pd.DataFrame()

    def refresh(self):
        df_c = self._get_complexes()
        if df_c.empty:
            self._summary_var.set("Brak danych — wczytaj plik Skocznie w zakładce 'Skocznie'.")
            return

        df_rows, _, _, _, _ = compute_complex_costs(df_c)

        # Uzupełnij _full_costs i _fis_classes
        for _, r in df_rows.iterrows():
            key = (str(r.get("Kraj", "")).strip().upper(), str(r.get("Miasto", "")).strip())
            self._full_costs[key] = int(pd.to_numeric(r.get("Suma", 0), errors="coerce") or 0)

        for _, r in df_c.iterrows():
            key = (str(r.get("Kraj", "")).strip().upper(), str(r.get("Miasto", "")).strip())
            self._fis_classes[key] = _compute_current_fis_class(r)

        # Wczytaj istniejące klasy operacyjne
        op_path = Path(self._path_var.get().strip())
        df_op = load_operational_classes(op_path)
        for _, r in df_op.iterrows():
            key = (str(r.get("Kraj", "")).strip().upper(), str(r.get("Miasto", "")).strip())
            self._data.setdefault(key, {"Klasa": "Pełna", "Sezony_POL": 0, "Sezony_MIN": 0})
            self._data[key]["Klasa"] = str(r.get("Klasa", "Pełna")).strip()
            self._data[key]["Sezony_POL"] = int(
                pd.to_numeric(r.get("Sezony_POL", 0), errors="coerce") or 0)
            self._data[key]["Sezony_MIN"] = int(
                pd.to_numeric(r.get("Sezony_MIN", 0), errors="coerce") or 0)

        self._render(df_rows)

    def _render(self, df_rows: pd.DataFrame):
        self._tv.delete(*self._tv.get_children())
        total_full = 0
        total_eff  = 0

        for _, r in df_rows.iterrows():
            kraj   = str(r.get("Kraj", "")).strip().upper()
            miasto = str(r.get("Miasto", "")).strip()
            key    = (kraj, miasto)

            entry      = self._data.get(key, {"Klasa": "Pełna", "Sezony_POL": 0, "Sezony_MIN": 0})
            klasa_op   = entry.get("Klasa", "Pełna")
            sezony_pol = entry.get("Sezony_POL", 0)
            sezony_min = entry.get("Sezony_MIN", 0)
            full_cost  = self._full_costs.get(key, 0)
            eff_cost   = int(full_cost * _OP_MULTIPLIERS.get(klasa_op, 1.0))
            fis_cls    = self._fis_classes.get(key, "—")
            eff_fis    = _effective_fis_class(fis_cls, klasa_op)

            total_full += full_cost
            total_eff  += eff_cost

            tags = []
            if klasa_op == "Minimalna":
                tags.append("min")
            elif klasa_op == "Połowiczna":
                tags.append("pol")
            # Warn: zbliżenie do progu degradacji (Połowiczna: 2/3, Minimalna: 1/2)
            if (klasa_op == "Połowiczna" and sezony_pol >= 2) or \
               (klasa_op == "Minimalna"  and sezony_min >= 1):
                tags.append("warn")

            self._tv.insert("", "end", iid=f"{kraj}|{miasto}", text=kraj,
                values=[miasto, fis_cls, eff_fis, klasa_op, sezony_pol, sezony_min,
                        f"{full_cost:,}".replace(",", " "),
                        f"{eff_cost:,}".replace(",", " ")],
                tags=tuple(tags))

        savings = total_full - total_eff
        self._summary_var.set(
            f"Koszt pełny: {total_full:,} €   •   Koszt efektywny: {total_eff:,} €"
            f"   •   Oszczędność: {savings:,} €".replace(",", " ")
        )

    # ── Akcje ────────────────────────────────────────────────────────────────

    def _bulk_apply(self):
        selected = self._tv.selection()
        if not selected:
            messagebox.showwarning("Brak wyboru", "Zaznacz wiersze w tabeli.", parent=self)
            return
        new_klasa = self._bulk_cb.get()
        for iid in selected:
            parts = iid.split("|", 1)
            if len(parts) == 2:
                key = (parts[0], parts[1])
                self._data.setdefault(key, {"Sezony_POL": 0, "Sezony_MIN": 0})
                self._data[key]["Klasa"] = new_klasa
        df_c = self._get_complexes()
        if not df_c.empty:
            df_rows, *_ = compute_complex_costs(df_c)
            self._render(df_rows)

    def _save(self):
        rows = [
            {"Kraj": k[0], "Miasto": k[1],
             "Klasa": v.get("Klasa", "Pełna"),
             "Sezony_POL": v.get("Sezony_POL", 0),
             "Sezony_MIN": v.get("Sezony_MIN", 0)}
            for k, v in self._data.items()
        ]
        df = pd.DataFrame(rows, columns=["Kraj", "Miasto", "Klasa", "Sezony_POL", "Sezony_MIN"])
        op_path = self._path_var.get().strip()
        save_operational_classes(df, op_path)
        self._ht._op_class_path = op_path
        messagebox.showinfo("Zapisano", f"Klasy operacyjne zapisane do:\n{op_path}", parent=self)

    def _season_end(self):
        if not messagebox.askyesno(
            "Zakończ sezon",
            "Przetworzyć koniec sezonu?\n"
            "• Połowiczna: Sezony_POL += 1; po 3 sezonach — degradacja infrastruktury\n"
            "• Minimalna:  Sezony_MIN += 1; po 2 sezonach — degradacja infrastruktury\n"
            "• Przejście między klasami zeruje licznik drugiej klasy",
            parent=self
        ):
            return

        rows = [
            {"Kraj": k[0], "Miasto": k[1],
             "Klasa": v.get("Klasa", "Pełna"),
             "Sezony_POL": v.get("Sezony_POL", 0),
             "Sezony_MIN": v.get("Sezony_MIN", 0)}
            for k, v in self._data.items()
        ]
        df_op = pd.DataFrame(rows, columns=["Kraj", "Miasto", "Klasa", "Sezony_POL", "Sezony_MIN"])

        hills_path_str = getattr(self._ht.hills_viewer, "var_path", tk.StringVar()).get().strip()
        df_op_new, messages = apply_season_end_degradation(df_op, hills_path_str)

        # Zaktualizuj _data
        for _, r in df_op_new.iterrows():
            key = (str(r["Kraj"]).strip().upper(), str(r["Miasto"]).strip())
            self._data.setdefault(key, {"Klasa": "Pełna"})
            self._data[key]["Sezony_POL"] = int(r.get("Sezony_POL", 0))
            self._data[key]["Sezony_MIN"] = int(r.get("Sezony_MIN", 0))

        op_path = self._path_var.get().strip()
        save_operational_classes(df_op_new, op_path)
        self._ht._op_class_path = op_path

        if messages:
            msg = "Degradacje w tym sezonie:\n" + "\n".join(f"  • {m}" for m in messages)
            msg += "\n\nPlik Skocznie zaktualizowany. Odśwież zakładkę Skocznie, by zobaczyć zmiany."
        else:
            msg = "Brak degradacji w tym sezonie.\nKlasy operacyjne i liczniki zaktualizowane."
        messagebox.showinfo("Zakończono sezon", msg, parent=self)

        df_c = self._get_complexes()
        if not df_c.empty:
            for _, r in df_c.iterrows():
                key = (str(r.get("Kraj", "")).strip().upper(), str(r.get("Miasto", "")).strip())
                self._fis_classes[key] = _compute_current_fis_class(r)
            df_rows, *_ = compute_complex_costs(df_c)
            self._render(df_rows)

    def _auto_op_classes(self):
        """Auto-przelicza klasy operacyjne z klasyfikacji poprzedniego sezonu."""
        # 1. Ustal numer sezonu z ścieżki pliku klasy operacyjnej
        op_path_str = self._path_var.get().strip()
        m = re.search(r'S(\d+)', op_path_str, re.IGNORECASE)
        if not m:
            messagebox.showerror("Błąd", "Nie można ustalić numeru sezonu ze ścieżki pliku.", parent=self)
            return
        cur_s_num = int(m.group(1))
        prev_s = f"S{cur_s_num - 1}"

        search_dirs = [
            Path(f"{prev_s}/Klasyfikacje {prev_s}"),
            Path(op_path_str).parent.parent / prev_s / f"Klasyfikacje {prev_s}",
        ]
        search_dir = next((d for d in search_dirs if d.exists()), search_dirs[0])

        # 2. Wczytaj kompleksy skoczni
        df_c = self._get_complexes()
        if df_c.empty:
            messagebox.showerror("Błąd", "Brak danych skoczni. Wczytaj plik Skocznie.", parent=self)
            return

        # 3. Oblicz demand per kraj
        country_demand, wc_demand = compute_op_class_demands(search_dir, prev_s)
        if not country_demand:
            messagebox.showwarning(
                "Brak danych klasyfikacji",
                f"Nie znaleziono plików klasyfikacji w:\n{search_dir.resolve()}\n\n"
                "Sprawdź czy folder z klasyfikacjami poprzedniego sezonu istnieje.",
                parent=self
            )
            return

        # 4. Zgrupuj skocznie per kraj, posortowane malejąco po pojemności
        country_hills: dict = {}
        for _, r in df_c.iterrows():
            nat = str(r.get("Kraj", "")).strip().upper()
            miasto = str(r.get("Miasto", "")).strip()
            poj = int(pd.to_numeric(r.get("Miejsca dla kibicow", 0), errors="coerce") or 0)
            country_hills.setdefault(nat, []).append((miasto, poj))
        for nat in country_hills:
            country_hills[nat].sort(key=lambda x: x[1], reverse=True)

        # 5. Wyznacz proponowane klasy
        proposed: dict = {}  # (nat, miasto) → klasa
        for nat, hills in country_hills.items():
            # Kraj z 1 skocznią → zawsze Pełna
            if len(hills) == 1:
                proposed[(nat, hills[0][0])] = "Pełna"
                continue
            demand = country_demand.get(nat, 0) + 1   # +1 slot juniorski
            total_active = min(math.ceil(demand / 2), len(hills))
            pełna_n = min(wc_demand.get(nat, 0), total_active)
            poł_n = total_active - pełna_n
            for i, (miasto, _) in enumerate(hills):
                if i < pełna_n:
                    klasa = "Pełna"
                elif i < pełna_n + poł_n:
                    klasa = "Połowiczna"
                else:
                    klasa = "Minimalna"
                proposed[(nat, miasto)] = klasa

        # 6. Znajdź obniżenia względem obecnych ustawień
        downgrades = []
        for (nat, miasto), new_cls in proposed.items():
            cur_cls = self._data.get((nat, miasto), {}).get("Klasa", "Pełna")
            if _CLASS_RANK.get(new_cls, 2) > _CLASS_RANK.get(cur_cls, 0):
                downgrades.append((nat, miasto, cur_cls, new_cls))

        # 7. Dialog z checkboxami dla obniżeń
        approved_downgrades: set = set()
        if downgrades:
            dlg = _DowngradeDialog(self, downgrades)
            self.wait_window(dlg)
            if dlg.cancelled:
                return
            approved_downgrades = dlg.approved
        else:
            approved_downgrades = set()

        # 8. Zastosuj proponowane klasy (blokuj niezatwierdzone obniżenia)
        downgrade_keys = {(n, m) for n, m, _, _ in downgrades}
        for (nat, miasto), new_cls in proposed.items():
            key = (nat, miasto)
            self._data.setdefault(key, {"Sezony_POL": 0, "Sezony_MIN": 0})
            if key in downgrade_keys and key not in approved_downgrades:
                # Użytkownik odznaczył → zachowaj obecną klasę
                pass
            else:
                self._data[key]["Klasa"] = new_cls

        # 9. Odśwież widok
        df_rows, *_ = compute_complex_costs(df_c)
        self._render(df_rows)
        blocked = len(downgrade_keys) - len(approved_downgrades)
        messagebox.showinfo(
            "Auto-przeliczanie gotowe",
            f"Przeliczono klasy dla {len(country_hills)} krajów.\n"
            f"Dane z klasyfikacji: {prev_s}\n"
            + (f"Zablokowano {blocked} obniżeń (zachowano obecną klasę).\n" if blocked else "")
            + "\nKliknij 'Zapisz', żeby utrwalić zmiany.",
            parent=self
        )

    def _pick_file(self):
        p = filedialog.askopenfilename(
            title="Wybierz plik klasy operacyjnej",
            filetypes=[("CSV", "*.csv"), ("Wszystkie", "*.*")],
            parent=self
        )
        if p:
            self._path_var.set(p)


class HillBuilderTab(ttk.Frame):
    """Zakładka: Budowa skoczni — formularz dodający nową skocznię do Skocznie S51.csv"""
    def __init__(self, parent, csv_path="S51/Skocznie S51.csv"):
        super().__init__(parent)
        p = Path(csv_path)
        if not p.is_absolute():
            # klucz: ścieżka wzg. folderu z hills_tab.py, identycznie jak w "Skocznie"
            p = Path(__file__).resolve().parent / p
        self.csv_path = p
        self._build_ui()

    def _build_ui(self):
        import tkinter as tk
        from tkinter import ttk

        # PanedWindow: lewy (dodawanie), prawy (rozbudowa/edycja)
        pan = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        pan.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # --- LEWO: to co miałeś (dodawanie nowej skoczni) ---
        left = ttk.Frame(pan)
        pan.add(left, weight=1)

        frm = ttk.Frame(left)
        frm.pack(fill="x", padx=12, pady=2)

        fields = [
            ("Reprezentacja", tk.Entry),
            ("Kraj", tk.Entry),
            ("Miasto", tk.Entry),
            ("Skocznia", tk.Entry),
            ("K", tk.Entry),
            ("HS", tk.Entry),
            ("Stan", ttk.Combobox, ["OTWARTA", "ZAMKNIĘTA"]),
            ("Homologacja", ttk.Combobox, ["CONTINENTAL CLASS", "WORLD CUP CLASS", "OLYMPIC "]),
            ("Miejsca dla kibiców", tk.Entry),
            ("OŚ", tk.Entry),
            ("Ig", ttk.Combobox, ["+", "-"]),
            ("Tw", ttk.Combobox, ["zwykła", "elektr."]),
            ("Kk", ttk.Combobox, ["-", "poz 1", "poz 2", "poz 3", "poz 4", "poz 5"]),
            ("Ks", ttk.Combobox, ["-", "+"]),
            ("Poc", ttk.Combobox, ["niski", "średni", "dobry", "wyborny", ""]),
            ("Sia", ttk.Combobox, ["-", "+"]),
            ("Naś", ttk.Combobox, ["-", "A", "B"]),
        ]
        self.inputs = {}
        for i, (label, widget_cls, *args) in enumerate(fields):
            ttk.Label(frm, text=label + ":").grid(row=i, column=0, sticky="e", padx=(0,6), pady=0)
            if widget_cls is ttk.Combobox:
                w = ttk.Combobox(frm, values=args[0], state="readonly", width=20)
                w.set(args[0][0])
            else:
                w = widget_cls(frm, width=22)
            w.grid(row=i, column=1, sticky="w", pady=0)
            self.inputs[label] = w

        # --- CHECKBOXY (tylko do kalkulacji kosztów; NIE zapisują się do CSV) ---
        self.build_flags = {
            "nowa":          tk.BooleanVar(value=False),
            "nowa_normalna": tk.BooleanVar(value=False),
            "nowa_duza":     tk.BooleanVar(value=False),
            "nowa_mamucia":  tk.BooleanVar(value=False),
            "nowa_kraj":     tk.BooleanVar(value=False),
        }

        frm_chk = ttk.LabelFrame(frm, text="Rodzaj inwestycji (na potrzeby kosztów)")
        frm_chk.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(2, 0))

        ttk.Checkbutton(frm_chk, text="1) Nowa skocznia",
                        variable=self.build_flags["nowa"]).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(frm_chk, text="2) Nowa skocznia normalna w kompleksie",
                        variable=self.build_flags["nowa_normalna"]).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(frm_chk, text="3) Nowa skocznia duża w kompleksie",
                        variable=self.build_flags["nowa_duza"]).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(frm_chk, text="4) Nowa skocznia mamucia w kompleksie",
                        variable=self.build_flags["nowa_mamucia"]).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(frm_chk, text="5) Nowa skocznia w kraju",
                        variable=self.build_flags["nowa_kraj"]).pack(anchor="w", padx=8, pady=2)

        # --- CHECKBOX: Nowa skocznia w kompleksie + lista skoczni do kopiowania danych ---
        self._kompleks_var = tk.BooleanVar(value=False)
        frm_kompleks = ttk.LabelFrame(frm, text="Nowa skocznia w kompleksie")
        frm_kompleks.grid(row=len(fields)+1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        ttk.Checkbutton(
            frm_kompleks,
            text="Uzupełnij dane z istniejącej skoczni w kompleksie",
            variable=self._kompleks_var,
            command=self._on_kompleks_toggle,
        ).pack(anchor="w", padx=8, pady=(4, 2))

        self._kompleks_cb_var = tk.StringVar()
        self._kompleks_cb = ttk.Combobox(
            frm_kompleks,
            textvariable=self._kompleks_cb_var,
            state="disabled",
            width=55,
        )
        self._kompleks_cb.pack(anchor="w", padx=8, pady=(0, 6), fill="x")
        self._kompleks_cb.bind("<<ComboboxSelected>>", lambda e: self._fill_from_kompleks())

        ttk.Button(frm, text="Dodaj skocznię", command=self._add_hill)\
            .grid(row=len(fields)+2, column=0, columnspan=2, pady=(5,0))
        
        # --- PRAWO: Rozbudowa/edycja istniejącej skoczni ---
        right = ttk.Frame(pan)
        pan.add(right, weight=1)

        top = ttk.Frame(right); top.pack(fill="x", padx=12, pady=(5,2))
        ttk.Label(top, text="Rozbudowa skoczni").pack(side="left")
        self._pick_var = tk.StringVar()
        self._pick_cb = ttk.Combobox(top, textvariable=self._pick_var, state="readonly", width=60)
        self._pick_cb.pack(side="left", padx=8)
        ttk.Button(top, text="Odśwież listę", command=self._reload_hills_list).pack(side="left")

        self._edit_wrap = ttk.Frame(right)
        self._edit_wrap.pack(fill="x", padx=12, pady=(2,2))

        # zbuduj taki sam zestaw pól jak po lewej, ale do edycji
        self.edit_inputs = self._build_fields(self._edit_wrap)
        ttk.Button(self._edit_wrap, text="Zapisz zmiany", command=self._save_edit)\
            .grid(row=len(fields), column=0, columnspan=2, pady=(5,0))

        # wstępne załadowanie listy do comboboxa
        self._reload_hills_list()
        self._pick_cb.bind("<<ComboboxSelected>>", lambda e: self._load_selected_into_form())

    def _on_kompleks_toggle(self):
        """Włącza/wyłącza listę skoczni do kopiowania danych."""
        if self._kompleks_var.get():
            # odśwież listę i odblokuj combobox
            df = self._read_hills_df()
            self._df_kompleks = df.copy()
            vals = df["_KEY_"].astype(str).tolist()
            self._kompleks_cb.configure(values=vals, state="readonly")
            if vals:
                self._kompleks_cb.current(0)
                self._fill_from_kompleks()
        else:
            self._kompleks_cb.configure(state="disabled")

    def _fill_from_kompleks(self):
        """Kopiuje dane z wybranej skoczni do formularza — wszystko poza Skocznia, K, HS."""
        if not hasattr(self, "_df_kompleks"):
            return
        key = self._kompleks_cb_var.get()
        if not key:
            return
        row = self._df_kompleks[self._df_kompleks["_KEY_"] == key]
        if row.empty:
            return
        r = row.iloc[0]

        # Pola które kopiujemy (wszystko poza Skocznia, K, HS)
        copy_fields = [
            "Reprezentacja", "Kraj", "Miasto", "Stan", "Homologacja",
            "Miejsca dla kibiców", "OŚ", "Ig", "Tw", "Kk", "Ks", "Poc", "Sia", "Naś",
        ]

        import pandas as pd
        for col in copy_fields:
            w = self.inputs.get(col)
            if w is None:
                continue
            val = "" if pd.isna(r.get(col, "")) else str(r.get(col, ""))
            try:
                w.set(val)          # Combobox
            except Exception:
                try:
                    w.delete(0, "end")
                    w.insert(0, val)    # Entry
                except Exception:
                    pass

    def _build_fields(self, parent):
        import tkinter as tk
        from tkinter import ttk
        spec = [
            ("Reprezentacja", tk.Entry, None),
            ("Kraj", tk.Entry, None),
            ("Miasto", tk.Entry, None),
            ("Skocznia", tk.Entry, None),
            ("K", tk.Entry, None),
            ("HS", tk.Entry, None),
            ("Stan", ttk.Combobox, ["OTWARTA", "ZAMKNIĘTA"]),
            ("Homologacja", ttk.Combobox, ["CONTINENTAL CLASS", "WORLD CUP CLASS", "OLYMPIC "]),
            ("Miejsca dla kibiców", tk.Entry, None),
            ("OŚ", tk.Entry, None),
            ("Ig", ttk.Combobox, ["+", "-"]),
            ("Tw", ttk.Combobox, ["zwykła", "elektr."]),
            ("Kk", ttk.Combobox, ["-", "poz 1", "poz 2", "poz 3", "poz 4", "poz 5"]),
            ("Ks", ttk.Combobox, ["-", "+"]),
            ("Poc", ttk.Combobox, ["niski", "średni", "dobry", "wyborny", ""]),
            ("Sia", ttk.Combobox, ["-", "+"]),
            ("Naś", ttk.Combobox, ["-", "A", "B"]),
        ]
        res = {}
        for i, (label, wcls, opts) in enumerate(spec):
            ttk.Label(parent, text=label + ":").grid(row=i, column=0, sticky="e", padx=(0,6), pady=0)
            if wcls is ttk.Combobox:
                w = ttk.Combobox(parent, values=opts, state="readonly", width=20)
                w.set(opts[0])
            else:
                w = wcls(parent, width=22)
            w.grid(row=i, column=1, sticky="w", pady=0)
            res[label] = w
        return res

    def _read_hills_df(self):
        import pandas as pd
        from pathlib import Path
        # przeczytaj CSV niezależnie od rozjechanych nagłówków/ogonków
        def _read_any(path: Path) -> pd.DataFrame:
            # tolerancyjny odczyt: engine='python', pomija zbugowane linie
            for enc in ("utf-8-sig", "utf-8", "cp1250", "iso-8859-2", "latin1"):
                try:
                    return pd.read_csv(
                        path,
                        sep=";",
                        encoding=enc,
                        engine="python",
                        on_bad_lines="skip",  # ignoruj linie z za dużą liczbą pól
                        dtype=str,            # ← WSZYSTKO jako tekst, zero NaN-ów
                    )
                except Exception:
                    continue
            return pd.read_csv(
                path,
                sep=";",
                encoding="latin1",
                engine="python",
                on_bad_lines="skip",
                dtype=str,                # ← tu też
            )


        from hills_tab import _canon_hdr  # u nas w tym samym pliku
        df = _read_any(self.csv_path)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame(columns=[
                "Reprezentacja","Kraj","Miasto","Skocznia","K","HS","Stan","Homologacja",
                "Miejsca dla kibiców","OŚ","Ig","Tw","Kk","Ks","Poc","Sia","Naś"
            ])

        # Zbuduj mapę nagłówków po znormalizowaniu (bez ogonków itp.)
        want = {
            "reprezentacja":"Reprezentacja","kraj":"Kraj","miasto":"Miasto","skocznia":"Skocznia",
            "k":"K","hs":"HS","stan":"Stan","homologacja":"Homologacja",
            "miejscadlakibicow":"Miejsca dla kibiców","os":"OŚ","ig":"Ig","tw":"Tw",
            "kk":"Kk","ks":"Ks","poc":"Poc","sia":"Sia","nas":"Naś"
        }
        mapping = {}
        for c in list(df.columns):
            k = _canon_hdr(c)
            if k in want and want[k] not in mapping.values():
                mapping[c] = want[k]
            else:
                mapping[c] = c
        df = df.rename(columns=mapping)

        # dobij brakujące kolumny
        for col in want.values():
            if col not in df.columns:
                df[col] = ""

        # klucz do comboboxa
        df["_KEY_"] = df.apply(lambda r: f"{r.get('Reprezentacja','')} | {r.get('Kraj','')} | {r.get('Miasto','')} | {r.get('Skocznia','')}", axis=1)
        return df

    def _reload_hills_list(self):
        df = self._read_hills_df()
        self._df_edit = df.copy()
        try:
            vals = df["_KEY_"].astype(str).tolist()
        except Exception:
            vals = []
        self._pick_cb.configure(values=vals)
        if vals:
            self._pick_cb.current(0)
            self._load_selected_into_form()
        else:
            # wyczyść formularz edycji
            for w in self.edit_inputs.values():
                try: w.set("")  # combobox
                except Exception:
                    try: w.delete(0, "end")
                    except Exception: pass

    def _load_selected_into_form(self):
        if not hasattr(self, "_df_edit"):
            return
        key = self._pick_var.get()
        if not key:
            return
        row = self._df_edit[self._df_edit["_KEY_"] == key]
        if row.empty:
            return
        r = row.iloc[0]
        def _set(name, val):
            w = self.edit_inputs.get(name)
            if w is None: return
            try: w.set("" if pd.isna(val) else str(val))
            except Exception:
                try:
                    w.delete(0, "end")
                    w.insert(0, "" if pd.isna(val) else str(val))
                except Exception: pass
        for col in ["Reprezentacja","Kraj","Miasto","Skocznia","K","HS","Stan","Homologacja",
                    "Miejsca dla kibiców","OŚ","Ig","Tw","Kk","Ks","Poc","Sia","Naś"]:
            _set(col, r.get(col, ""))

    def _parse_int(self, val):
        import pandas as pd
        if val is None:
            return pd.NA
        s = str(val).replace("\xa0", "").replace(" ", "").strip()  # usuń spacje w tysiącach
        if s in ("", "-"):
            return pd.NA
        # akceptuj „200”, „200.0”, „200,0”
        s = s.replace(",", ".")
        try:
            return int(float(s))
        except Exception:
            return pd.NA

    def _assign_typed(self, i, h, v):
        import pandas as pd
        # liczby trzymamy tylko dla K i HS, reszta jako tekst
        INT_COLS = {"K", "HS"}
        # Kolumny licznikowe, które w pliku mają mieć spację w tysiącach ("36 100", "1 000")
        THOUSAND_STR_COLS = {"Miejsca dla kibiców", "OŚ"}
        FLOAT_COLS = set()
        if h in THOUSAND_STR_COLS:
            # parsujemy wartość tylko po to, żeby ją znormalizować,
            # ale w DF trzymamy jako string z odstępami
            n = self._parse_int(v)
            if n is None or pd.isna(n):
                self._df_edit.at[i, h] = ""
            else:
                try:
                    n_int = int(n)
                except Exception:
                    n_int = 0
                s = f"{n_int:,}".replace(",", " ").replace("\u00a0", " ")
                self._df_edit.at[i, h] = s

        elif h in INT_COLS:
            # Pandas 2.x nie pozwala wpisać int do kolumny StringDtype –
            # konwertujemy kolumnę do object żeby przyjęła dowolny typ.
            n = self._parse_int(v)
            if h in self._df_edit.columns and hasattr(self._df_edit[h], "dtype"):
                import pandas.api.types as pat
                if pat.is_string_dtype(self._df_edit[h]) or str(self._df_edit[h].dtype) in ("string", "StringDtype"):
                    self._df_edit[h] = self._df_edit[h].astype(object)
            self._df_edit.at[i, h] = pd.NA if (n is None or pd.isna(n)) else int(n)

        elif h in FLOAT_COLS:
            # analogicznie dla float – konwertuj kolumnę do object jeśli potrzeba
            try:
                vv = float(str(v).replace(",", "."))
            except Exception:
                vv = float("nan")
            if h in self._df_edit.columns and hasattr(self._df_edit[h], "dtype"):
                import pandas.api.types as pat
                if pat.is_string_dtype(self._df_edit[h]) or str(self._df_edit[h].dtype) in ("string", "StringDtype"):
                    self._df_edit[h] = self._df_edit[h].astype(object)
            self._df_edit.at[i, h] = vv

        else:
            self._df_edit.at[i, h] = "" if v is None else str(v)

    def _save_edit(self):
        import pandas as pd
        from pathlib import Path
        from tkinter import messagebox

        if not hasattr(self, "_df_edit") or self._df_edit.empty:
            messagebox.showwarning("Uwaga", "Brak danych do zapisania.")
            return

        key = self._pick_var.get()
        if not key:
            messagebox.showwarning("Uwaga", "Wybierz skocznię z listy.")
            return

        HEADERS = ["Reprezentacja","Kraj","Miasto","Skocznia","K","HS","Stan","Homologacja",
                "Miejsca dla kibiców","OŚ","Ig","Tw","Kk","Ks","Poc","Sia","Naś"]

        # zaciągnij wartości z prawego formularza (STAN PO)
        new_vals = {h: (self.edit_inputs.get(h).get().strip() if hasattr(self.edit_inputs.get(h), "get") else "")
                    for h in HEADERS}

        # znajdź wiersz
        idxs = self._df_edit.index[self._df_edit["_KEY_"] == key]
        if len(idxs) == 0:
            messagebox.showwarning("Uwaga", "Nie znaleziono wybranej skoczni w danych.")
            return
        i = int(idxs[0])

        # STAN PRZED — złap przed modyfikacją!
        old_vals = {h: (self._df_edit.at[i, h] if h in self._df_edit.columns else "") for h in HEADERS}

        # PODMIEŃ NA NOWE (teraz dopiero)
        for h, v in new_vals.items():
            self._assign_typed(i, h, v)

        # przelicz klucz (na wypadek zmiany)
        self._df_edit.at[i, "_KEY_"] = f"{self._df_edit.at[i,'Reprezentacja']} | {self._df_edit.at[i,'Kraj']} | {self._df_edit.at[i,'Miasto']} | {self._df_edit.at[i,'Skocznia']}"

        # helper do formatowania liczb z odstępem tysięcy
        def _fmt_thousands_from_any(x):
            s = str(x).strip()
            if s in ("", "-", "\u2013", "nan", "NaN"):
                return ""
            v = _to_int_safe(x)
            if v == 0 and s == "":
                return ""
            txt = f"{v:,}".replace(",", " ").replace("\u00a0", " ")
            return txt

        # ZAPISZ GŁÓWNY CSV (ANSI, raz)
        try:
            df_out = self._df_edit.drop(
                columns=[c for c in ["_KEY_"] if c in self._df_edit.columns]
            ).copy()

            from hills_tab import _to_int_safe  # jesteśmy w tym samym pliku, ale to jest czytelne

            for col in ["Miejsca dla kibiców", "OŚ"]:
                if col in df_out.columns:
                    df_out[col] = df_out[col].map(_fmt_thousands_from_any).astype("object")

            df_out.to_csv(self.csv_path, sep=";", index=False, encoding="cp1250")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać zmian:\n{e}")
            return

        # ── PROPAGACJA KOLUMN WSPÓLNYCH KOMPLEKSU ────────────────────────────
        # Kolumny wspólne dla całego kompleksu (Reprezentacja + Kraj + Miasto)
        COMPLEX_COLS = ["Miejsca dla kibiców", "OŚ", "Tw", "Kk", "Ks", "Poc", "Sia", "Naś"]

        rep  = self._df_edit.at[i, "Reprezentacja"] if "Reprezentacja" in self._df_edit.columns else ""
        kraj = self._df_edit.at[i, "Kraj"]           if "Kraj"           in self._df_edit.columns else ""
        msto = self._df_edit.at[i, "Miasto"]         if "Miasto"         in self._df_edit.columns else ""

        mask_complex = (
            (self._df_edit.get("Reprezentacja", pd.Series([""] * len(self._df_edit))) == rep) &
            (self._df_edit.get("Kraj",           pd.Series([""] * len(self._df_edit))) == kraj) &
            (self._df_edit.get("Miasto",         pd.Series([""] * len(self._df_edit))) == msto)
        )
        siostry_idx = [j for j in self._df_edit.index[mask_complex] if j != i]

        # Wykryj które kolumny kompleksowe faktycznie się zmieniły
        changed_complex = []
        for col in COMPLEX_COLS:
            if col not in self._df_edit.columns:
                continue
            old_v = str(old_vals.get(col, "")).strip()
            new_v = str(new_vals.get(col, "")).strip()
            if old_v != new_v:
                changed_complex.append(col)

        siostry_names = []
        if siostry_idx and changed_complex:
            for j in siostry_idx:
                for col in changed_complex:
                    self._assign_typed(j, col, new_vals.get(col, ""))
                name = self._df_edit.at[j, "Skocznia"] if "Skocznia" in self._df_edit.columns else str(j)
                siostry_names.append(str(name))

            # Zapisz CSV ponownie z propagowanymi wartościami
            try:
                df_out2 = self._df_edit.drop(
                    columns=[c for c in ["_KEY_"] if c in self._df_edit.columns]
                ).copy()
                for col in ["Miejsca dla kibiców", "OŚ"]:
                    if col in df_out2.columns:
                        df_out2[col] = df_out2[col].map(_fmt_thousands_from_any).astype("object")
                df_out2.to_csv(self.csv_path, sep=";", index=False, encoding="cp1250")
            except Exception:
                pass

        # DOPISZ LOG ROZBUDOWY: PRZED i PO
        try:
            self._append_rebuild_snapshots(old_vals, new_vals)
        except Exception as e:
            messagebox.showwarning("Uwaga", f"Zapis zmian OK, ale nie dopisano logu do 'Rozbudowa S51.csv':\n{e}")

        # Komunikat końcowy
        if siostry_names and changed_complex:
            cols_txt = ", ".join(changed_complex)
            hills_lines = ["  - " + n for n in siostry_names]
            hills_txt = "\n".join(hills_lines)
            msg = (
                "Zapisano zmiany do: " + str(self.csv_path) + "\n\n"
                + "Zaktualizowano kolumny [" + cols_txt + "]\n"
                + "w pozostalych skoczniach kompleksu:\n"
                + hills_txt
            )
            messagebox.showinfo("Sukces", msg)
        else:
            messagebox.showinfo("Sukces", "Zapisano zmiany do: " + str(self.csv_path))

        try:
            # HillsTab nasłuchuje na ten event i sama wywoła przeliczenie kosztów
            self.master.event_generate("<<HILLS_COMPLEXES_REFRESH>>", when="tail")
        except Exception:
            pass

        # powiadom i odśwież UI
        try:
            self.event_generate("<<HILLS_COMPLEXES_REFRESH>>", when="tail")
        except Exception:
            pass
        self._reload_hills_list()
        try:
            self._pick_cb.set(self._df_edit.at[i, "_KEY_"])
        except Exception:
            pass

    def _append_rebuild_snapshots(self, before_row: dict, after_row: dict):
        from pathlib import Path
        import csv
        from datetime import datetime
        import pandas as pd

        HEADERS = ["Reprezentacja","Kraj","Miasto","Skocznia","K","HS","Stan","Homologacja",
                   "Miejsca dla kibiców","OŚ","Ig","Tw","Kk","Ks","Poc","Sia","Naś"]
        # Dodajemy kolumnę Cena do nagłówków
        LOG_HEADERS = ["TS","Stan"] + HEADERS + ["Typ inwestycji", "Cena"]

        out_path = Path(self.csv_path).with_name("Rozbudowa S51.csv")
        new_file = not out_path.exists() or out_path.stat().st_size == 0
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Używamy wyciągniętej funkcji globalnej
        calculated_cost = _rebuild_cost(pd.Series(before_row), pd.Series(after_row))

        def row_to_list(snapshot_dict, label, cost_val):
            return (
                [ts, label]
                + [str(snapshot_dict.get(h, "")).strip() for h in HEADERS]
                + ["Rozbudowa", cost_val]
            )

        with open(out_path, "a", encoding="cp1250", newline="") as f:
            w = csv.writer(f, delimiter=";")
            if new_file:
                w.writerow(LOG_HEADERS)
            w.writerow(row_to_list(before_row, "PRZED", 0))
            w.writerow(row_to_list(after_row, "PO", calculated_cost))

    def _investment_type_text_build(self) -> str:
        """
        Budowa: opis typu inwestycji na podstawie checkboxów po lewej.
        Jeśli nic nie zaznaczono, zwraca '—'.
        """
        label = []
        mapping = {
            "nowa":          "Nowa skocznia",
            "nowa_normalna": "Nowa skocznia normalna w kompleksie",
            "nowa_duza":     "Nowa skocznia duża w kompleksie",
            "nowa_mamucia":  "Nowa skocznia mamucia w kompleksie",
            "nowa_kraj":     "Nowa skocznia w kraju",
        }
        for key, text in mapping.items():
            try:
                if key in self.build_flags and self.build_flags[key].get():
                    label.append(text)
            except Exception:
                pass
        return ", ".join(label) if label else "—"

    def _append_build_entry(self, row_dict):
        from pathlib import Path
        import csv
        from datetime import datetime
        import pandas as pd

        HEADERS = ["Reprezentacja","Kraj","Miasto","Skocznia","K","HS","Stan","Homologacja",
                   "Miejsca dla kibiców","OŚ","Ig","Tw","Kk","Ks","Poc","Sia","Naś"]
        LOG_HEADERS = ["TS","Stan"] + HEADERS + ["Typ inwestycji", "Cena"]

        out_path = Path(self.csv_path).with_name("Rozbudowa S51.csv")
        new_file = not out_path.exists() or out_path.stat().st_size == 0
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        typ_inv = self._investment_type_text_build()
        
        # Obliczamy cenę używając globalnych funkcji
        ser = pd.Series({**row_dict, "Typ inwestycji": typ_inv})
        base = _snapshot_base_cost(ser)
        final_cost = _add_investment_extras(ser, base)

        with open(out_path, "a", encoding="cp1250", newline="") as f:
            w = csv.writer(f, delimiter=";")
            if new_file:
                w.writerow(LOG_HEADERS)
            w.writerow(
                [ts, "BUDOWA"]
                + [str(row_dict.get(h, "")).strip() for h in HEADERS]
                + [typ_inv, final_cost]
            )

    def _add_hill(self):
        import csv
        from pathlib import Path
        import tkinter as tk
        from tkinter import messagebox

        # ——— 1) Stały schemat kolumn (dokładnie taki jak w Twoim pliku) ———
        HEADERS = [
            "Reprezentacja","Kraj","Miasto","Skocznia","K","HS","Stan","Homologacja",
            "Miejsca dla kibiców","OŚ","Ig","Tw","Kk","Ks","Poc","Sia","Naś"
        ]

        # ——— 2) Lokalny helper: wykryj kodowanie istniejącego pliku ———
        def _detect_csv_encoding(path: Path) -> str:
            encs = ("utf-8-sig", "utf-8", "cp1250", "iso-8859-2", "latin1")
            try:
                data = path.read_bytes()[:8192]
            except Exception:
                return "utf-8-sig"
            for enc in encs:
                try:
                    data.decode(enc)
                    return enc
                except Exception:
                    continue
            return "latin1"

        # ——— 3) Zbierz dane z formularza i walidacja ———
        val = {label: w.get().strip() for label, w in self.inputs.items()}
        if not val.get("Miasto") or not val.get("Skocznia"):
            messagebox.showwarning("Uwaga", "Wymagane pola: Miasto i Skocznia.")
            return

        # ——— 4) Zbuduj wiersz zgodnie z HEADERS (lekka normalizacja) ———
        row = {h: "" for h in HEADERS}
        row["Reprezentacja"]       = val.get("Reprezentacja", "")
        row["Kraj"]                = (val.get("Kraj", "") or val.get("K", "")).upper()
        row["Miasto"]              = val.get("Miasto", "")
        row["Skocznia"]            = val.get("Skocznia", "")
        row["K"]                   = val.get("K", "")
        row["HS"]                  = val.get("HS", "")
        row["Stan"]                = val.get("Stan", "")
        row["Homologacja"]         = val.get("Homologacja", "")
        row["Miejsca dla kibiców"] = val.get("Miejsca dla kibiców", "")
        row["OŚ"]                  = val.get("OŚ", "")
        row["Ig"]                  = val.get("Ig", "")
        row["Tw"]                  = val.get("Tw", "")
        row["Kk"]                  = val.get("Kk", "")
        row["Ks"]                  = val.get("Ks", "")
        row["Poc"]                 = val.get("Poc", "")
        row["Sia"]                 = val.get("Sia", "")
        row["Naś"]                 = val.get("Naś", "")

        # ——— 5) Ścieżka docelowa i tryb tworzenia/appendu ———
        p: Path = self.csv_path if isinstance(self.csv_path, Path) else Path(self.csv_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        new_file = not p.exists()

        try:
            if new_file:
                # Nowy plik: twórz w UTF-8-SIG, Excel będzie szczęśliwy
                with open(p, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(HEADERS)
                    w.writerow([row[h] for h in HEADERS])
            else:
                # Istniejący plik: trzymaj jego kodowanie i sprawdź nagłówki
                file_enc = _detect_csv_encoding(p)

                with open(p, "r", encoding=file_enc, newline="") as f:
                    first_line = f.readline()
                if first_line.startswith("\ufeff"):
                    first_line = first_line.lstrip("\ufeff")
                found_headers = first_line.rstrip("\r\n").split(";")

                if found_headers != HEADERS:
                    messagebox.showerror(
                        "Błąd",
                        "Nagłówki w pliku różnią się od oczekiwanych.\n"
                        "Nie dopisuję wiersza, żeby nie popsuć formatu.\n\n"
                        f"W pliku: {found_headers}\nOczekiwane: {HEADERS}"
                    )
                    return

                # Dopisz jeden wiersz w tym samym kodowaniu i z tym samym separatorem
                with open(p, "a", encoding=file_enc, newline="") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow([row[h] for h in HEADERS])

            messagebox.showinfo("Sukces", f"Dopisano skocznię do:\n{p}")
            
            try:
                # HillsTab nasłuchuje na ten event i sama wywoła przeliczenie kosztów
                self.master.event_generate("<<HILLS_COMPLEXES_REFRESH>>", when="tail")
            except Exception:
                pass

            try:
                self._append_build_entry(row)  # ← to dopisze wiersz typu "BUDOWA" do Rozbudowa S51.csv
            except Exception as e:
                messagebox.showwarning(
                    "Uwaga",
                    f"Dopisano skocznię, ale nie zapisano logu do 'Rozbudowa S51.csv':\n{e}"
                )

            # Czyść pola tekstowe (comboboksy zostaw)
            for w in self.inputs.values():
                try:
                    if isinstance(w, tk.Entry):
                        w.delete(0, tk.END)
                except Exception:
                    pass

            # Opcjonalne odświeżenie innych zakładek, jeśli nasłuchują
            try:
                self.event_generate("<<HILLS_COMPLEXES_REFRESH>>")
            except Exception:
                pass

        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"{e}\n\nPlik:\n{p}")


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Demo – Skocznie + Infrastruktura")
    root.geometry("1100x640")
    nb = ttk.Notebook(root); nb.pack(fill="both", expand=True)
    tab = ttk.Frame(nb); nb.add(tab, text="Moduł")

    HillsTab(
        tab,
        default_hills=Path("./S51/Skocznie S51.csv"),
        default_infra=Path("./S51/Infrastruktura S51.csv"),
        default_complexes=Path("./S51/Kompleksy S51.csv"),
        flags_dir=Path("./flags"),
    ).pack(fill="both", expand=True)

    root.mainloop()
