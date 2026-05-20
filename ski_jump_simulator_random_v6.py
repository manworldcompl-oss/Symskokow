
# ski_jump_simulator_random_v6.py
# ---------------------------------------------------------------
# v6: Jeden plik, dwa tryby konkursu:
#     (A) klasyczny wielo-rundowy (--round-cuts "50,30" itd.)
#     (B) KO (Turniej 4 Skoczni) --ko
# Dodatkowo: AR(1) wiatr, rozdział takeoff/flight, skorelowani sędziowie,
#            płynny elite-regress oraz randomness bez limitu (>1.0 możliwe).
# W trybie KO zapisywane są dodatkowe arkusze: "KO – Pary (R1)" oraz "KO – Lucky Losers".
# ---------------------------------------------------------------

from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import re
import sys

def _sanitize_df_STRONG(df) -> pd.DataFrame:
    """
    Bardzo ostrożne czyszczenie przed zapisem do XLSX:
    - wymusza typ DataFrame
    - usuwa znaki niedozwolone w XML (ASCII control 0x00-0x1F bez \t,\n,\r)
    - przycina zbyt długie komórki do 32760 znaków (limit Excela 32767)
    - zamienia inf/-inf na NaN
    - konwertuje obiekty złożone (list/dict/tuple/set, bytes) do krótkiego str
    - konwertuje daty/czas/period/timedelta do string
    - normalizuje nagłówki kolumn
    """
    import numpy as np
    import pandas as pd
    import datetime as _dt

    MAXLEN = 32760

    if df is None:
        return pd.DataFrame()

    try:
        out = pd.DataFrame(df).copy()
    except Exception:
        out = pd.DataFrame()

    # Nagłówki
    def _clean_header(x: str) -> str:
        s = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", str(x))
        return s[:255] if len(s) > 255 else s  # nagłówek też skróć rozsądnie

    out.columns = [_clean_header(c) for c in out.columns]

    # Zamiana inf
    out = out.replace([np.inf, -np.inf], np.nan)

    # Funkcja czyszcząca komórki
    def _cell(x):
        # None / NaN
        try:
            import math
            if x is None or (isinstance(x, float) and math.isnan(x)):
                return ""
        except Exception:
            pass

        # numpy scalars
        try:
            import numpy as _np
            if isinstance(x, (_np.integer, _np.floating, _np.bool_)):
                return x.item()
        except Exception:
            pass

        # datetime / date / time / timedelta / Period
        try:
            import pandas as _pd
            if isinstance(x, (_dt.datetime, _dt.date, _dt.time, _dt.timedelta, _pd.Period)):
                return str(x)
        except Exception:
            pass

        # bytes
        if isinstance(x, (bytes, bytearray)):
            x = x.decode("utf-8", errors="replace")

        # złożone typy → str
        if isinstance(x, (list, dict, set, tuple)):
            x = str(x)

        s = str(x)

        # Usuń niedozwolone kontrolne (zostaw \t, \n, \r)
        s = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", s)

        # Przytnij do limitu Excela
        if len(s) > MAXLEN:
            s = s[:MAXLEN]
        return s

    # Zastosuj do kolumn obiektowych i mieszanych
    for c in out.columns:
        if out[c].dtype == "object" or str(out[c].dtype).startswith(("string", "category")):
            out[c] = out[c].map(_cell)
    return out

DEFAULT_EXCEL = "S44/Zawodnicy S44gpt.csv"
DEFAULT_OUTDIR = "."
FLAGS_DIR = "./flags"

# --- FIS points (1..30) ---
_FIS_POINTS = [100,80,60,50,45,40,36,32,29,26,24,22,20,18,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1]

def _fis_points_for_place(place_series):
    import pandas as pd
    s = pd.to_numeric(place_series, errors="coerce").fillna(0).astype(int)
    return s.map(lambda x: _FIS_POINTS[x-1] if 1 <= x <= 30 else 0)

# === Helper: miejsca ex aequo =====================================
def _apply_tied_places(
    df: pd.DataFrame,
    points_col: str,
    place_col: str = "Miejsce",
    ascending: bool = False,
    decimals: int = 1,
) -> pd.DataFrame:
    """
    Miejsca ex aequo na kluczu całkowitym: key = round(points * 10^decimals).
    Unikamy błędów float (np. 299.79999). Dodatkowo normalizujemy kolumnę 'Punkty'.
    """
    if df is None or df.empty or points_col not in df.columns:
        return df

    out = df.copy()
    s = pd.to_numeric(out[points_col], errors="coerce").fillna(0.0)

    scale = 10 ** int(decimals)
    key = np.rint(s.to_numpy() * scale).astype(np.int64)      # ← twarde „szufladki”
    key_s = pd.Series(key, index=out.index)

    # Nadpisz 'Miejsce' wg klucza (metoda 'min' = 1,1,3…; daj 'dense' jeśli chcesz 1,1,2…)
    if place_col in out.columns:
        out.drop(columns=[place_col], inplace=True)
    out.insert(0, place_col, key_s.rank(method="min", ascending=ascending).astype(int))

    # Nadpisz kolumnę punktów wersją po normalizacji (np. 1 miejsce po przecinku)
    out[points_col] = (key.astype(np.float64) / scale).round(decimals)

    return out

# ==================================================================

RNG = np.random.default_rng()

def load_roster(path: Path) -> pd.DataFrame:
    """
    Wczytuje bazę zawodników w 'nowym' formacie z pliku Zawodnicy S44gpt.xlsx,
    ale zachowuje kompatybilność wsteczną (stary układ kolumn też zadziała).
    Zwraca pełny DataFrame z kolumnami, jeśli są dostępne:
    ['Zawodnik','Kraj','Płeć','JUN/SEN','Wiek','UM','Forma','PrawoStartu','Kontuzja'].
    Silnik do obliczeń używa nadal UM/Forma/Kraj/Zawodnik — reszta jest głównie dla GUI.
    """
    import unicodedata, re as _re

    def _norm(s: str) -> str:
        s = str(s or "").strip().lower()
        # usuwamy diakrytyki i spacje/znaki nieliterowe
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = _re.sub(r"[^a-z0-9]+", "", s)
        return s

    # mapowanie nagłówków -> nazwy kanoniczne
    CANON = {
        "zawodnik": "Zawodnik",
        "name": "Zawodnik",
        "kraj": "Kraj",
        "country": "Kraj",
        "plec": "Płeć",
        "junsen": "JUN/SEN",
        "wiek": "Wiek",
        "um": "UM",
        "forma": "Forma",
        "prawostartu": "PrawoStartu",
        "kontuzja": "Kontuzja",
    }

    # 1) Wczytaj
    if path and Path(path).exists():
        p_str = str(path).lower()
        try:
            if p_str.endswith(".csv") or p_str.endswith(".txt"):
                # CSV: wykryj separator i BOM, spróbuj kilka popularnych kodowań
                last_err = None
                for enc in ("utf-8-sig", "utf-8", "cp1250"):
                    try:
                        df_raw = pd.read_csv(path, sep=None, engine="python", encoding=enc)
                        break
                    except Exception as e:
                        last_err = e
                        df_raw = None
                if df_raw is None:
                    # awaryjnie: średnik
                    df_raw = pd.read_csv(path, sep=";", engine="python")
            else:
                # Excel jak dotąd
                df_raw = pd.read_excel(path)
        except Exception as e:
            raise RuntimeError(f"Nie udało się wczytać pliku z zawodnikami: {e}")
    else:
        # awaryjna mini-baza (gdyby ktoś uruchomił bez pliku)
        df_raw = pd.DataFrame([
            {"Zawodnik": "Jan Kowalski", "UM": 90, "Forma": 90, "Kraj": "POL"},
            {"Zawodnik": "Piotr Nowak",  "UM": 70, "Forma": 72, "Kraj": "POL"},
            {"Zawodnik": "Lukas Steiner","UM": 75, "Forma": 68, "Kraj": "AUT"},
        ])

    # 2) Znormalizuj nagłówki → nazwy kanoniczne
    new_cols = []
    for c in df_raw.columns:
        key = _norm(c)
        new_cols.append(CANON.get(key, str(c)))
    df = df_raw.copy()
    df.columns = new_cols

    # 3) Zapewnij istnienie podstawowych kolumn
    essentials = ["Zawodnik", "Kraj", "UM", "Forma"]
    for col in essentials:
        if col not in df.columns:
            if col == "Kraj":
                df[col] = "N/A"
            elif col in ("UM", "Forma"):
                df[col] = 50
            else:
                df[col] = df.index.astype(str)

    # 4) Delikatne rzutowania typów (nie zbijamy GUI)
    num_cols = ["UM", "Forma", "Wiek", "PrawoStartu", "Kontuzja"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 5) Wypelnij braki sensownymi wartościami
    df["UM"] = pd.to_numeric(df["UM"], errors="coerce").fillna(50)
    df["Forma"] = pd.to_numeric(df["Forma"], errors="coerce").fillna(50)
    if "Kraj" in df.columns:
        df["Kraj"] = df["Kraj"].fillna("").astype(str).str.upper()

    # 6) Ustal przyjazną kolejność kolumn dla zakładki "Zawodnicy"
    preferred_order = [
        "Zawodnik", "Kraj", "Płeć", "JUN/SEN", "Wiek", "UM", "Forma", "PrawoStartu", "Kontuzja"
    ]
    ordered = [c for c in preferred_order if c in df.columns]
    tail = [c for c in df.columns if c not in ordered]
    df = df[ordered + tail].copy()

    return df

def _ability_rank_offset(um: pd.Series, forma: pd.Series) -> np.ndarray:
    um = pd.to_numeric(um, errors='coerce').fillna(50)
    forma = pd.to_numeric(forma, errors='coerce').fillna(50)
    ability = 0.65 * um + 0.35 * forma
    norm = np.clip(ability / 100.0, 0.0, 1.0)
    offset = -55.0 + 69.0 * norm  # [-55, +14] m
    return offset

def _soft_limit_params(HS: float, randomness: float):
    try:
        hs = float(HS)
    except Exception:
        hs = 140.0
    margin = float(max(2.0, min(10.0, 0.03 * hs)))
    scale = min(1.0, max(0.0, hs / 240.0))
    lin = 0.45 + 0.15 * scale + 0.15 * max(0.0, randomness)
    quad = 0.018 + 0.012 * scale + 0.010 * max(0.0, randomness)
    return margin, lin, quad

def compute_meter_value(K: float) -> float:
    try:
        k = float(K)
    except Exception:
        k = 120.0
    if k >= 160:
        return 1.2
    elif 101 <= k <= 159:
        return 1.8
    else:
        return 2.0

def smooth_ramp(x: np.ndarray, lo: float = 0.80, hi: float = 1.00) -> np.ndarray:
    t = (x - lo) / max(1e-9, (hi - lo))
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)  # smootherstep

def _wind_ar1(n: int, mean: float, sd: float, phi: float, rng: np.random.Generator) -> np.ndarray:
    w = np.zeros(n)
    w[0] = rng.normal(mean, sd)
    eps_sd = sd * np.sqrt(max(0.0, 1.0 - phi**2))
    for i in range(1, n):
        w[i] = mean + phi * (w[i-1] - mean) + rng.normal(0.0, eps_sd)
    return w

def simulate_round(
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
    rng: np.random.Generator | None = None,
    randomness: float = 0.35,
    elite_regress: float = 1.0,
    wind_phi: float = 0.75,
    wind_takeoff_gain: float = 0.5,
    wind_flight_gain: float = 2.2,
    judges_rho: float = 0.55,
    sort_output: bool = True,
) -> pd.DataFrame:
    rng_loc = rng or RNG

    base_offset = _ability_rank_offset(roster["UM"], roster["Forma"])
    base_perf = K + base_offset

    n = len(roster)
    ability_val = 0.65 * pd.to_numeric(roster['UM'], errors='coerce').fillna(50).to_numpy() +                   0.35 * pd.to_numeric(roster['Forma'], errors='coerce').fillna(50).to_numpy()
    ability_norm = np.clip(ability_val / 100.0, 0.0, 1.0)

    hill_gap = max(0.0, float(HS) - float(K)) if HS is not None else 0.0
    base_perf = base_perf + (ability_norm**2) * (0.60 * hill_gap)

    day_sigma = 0.015 + 0.025 * randomness
    day_form = rng_loc.normal(1.0, day_sigma, size=n)
    base_perf = K + (base_perf - K) * day_form

    # Wiatr AR(1)
    wind_ar = _wind_ar1(n, wind_ms_mean, wind_ms_sd, wind_phi, rng_loc)

    # Podział na takeoff/flight (turbulencja)
    takeoff_turb = rng_loc.normal(0.0, 0.30 * wind_ms_sd, size=n)
    flight_turb = rng_loc.normal(0.0, 0.50 * wind_ms_sd, size=n)
    wind_takeoff = wind_ar + takeoff_turb
    wind_flight = wind_ar + flight_turb

    # Belka z heurystyką na wiatr
    gate = np.full(n, int(gate_base), dtype=int)
    for i in range(n):
        if rng_loc.random() < p_gate_change:
            if wind_flight[i] < -0.5:
                delta = +1
            elif wind_flight[i] > 0.5:
                delta = -1
            else:
                delta = rng_loc.choice([-1, +1])
            gate[i] = int(np.clip(gate_base + delta, gate_base - max_gate_delta, gate_base + max_gate_delta))

    # Odległość: baza + wiatr (najazd + lot)
    distance = base_perf + wind_takeoff * wind_takeoff_gain + wind_flight * (wind_flight_gain + 0.4 * randomness)

    # Kompresja słabych
    comp = 0.75 + 0.25 * np.power(ability_norm, 0.5)
    distance = K + (distance - K) * comp

    # Kara dla słabych na dużych skoczniach
    weak_factor = (1.0 - ability_norm)
    distance -= (1.25 * weak_factor**2) * hill_gap

    # Szoki
    shock_prob = 0.02 + 0.10 * randomness
    shock_mask = rng_loc.random(n) < shock_prob
    if shock_mask.any():
        shocks = rng_loc.standard_t(df=3, size=shock_mask.sum()) * (1.8 + 1.2 * randomness)
        distance[shock_mask] += shocks

    # Płynny elite-regress
    w = smooth_ramp(ability_norm, 0.80, 1.00)
    base_p_bad = np.clip(0.03 + randomness * (0.05 + 0.12 * ability_norm), 0.0, 1.0)
    takeoff_penal = 1.0 + 0.12 * np.maximum(0.0, -wind_takeoff)  # tylni wiatr na progu
    elite_mult = 1.0 + 0.6 * max(0.0, elite_regress) * w
    p_bad_takeoff = np.clip(base_p_bad * elite_mult * takeoff_penal, 0.0, 0.80)

    bad_mask = rng_loc.random(n) < p_bad_takeoff
    if bad_mask.any():
        elite_strength = 1.0 + 0.9 * max(0.0, elite_regress) * w[bad_mask]
        penalty_base = 2.5 + 6.5 * ability_norm[bad_mask]
        penalty = rng_loc.normal(penalty_base, 1.4 + 0.6 * randomness, size=bad_mask.sum()) * elite_strength
        distance[bad_mask] -= penalty

    # Perfect jump
    if HS is not None:
        perfect_mask = (rng_loc.random(n) < (1.0/800.0))
        strong = ability_norm > 0.90
        good_base = distance > (HS + 5)
        perf_idx = perfect_mask & strong & good_base
        if np.any(perf_idx):
            distance[perf_idx] = distance[perf_idx] + rng_loc.normal(4.0, 1.0, size=perf_idx.sum())

    # Soft-limit powyżej HS
    if HS is not None:
        margin, lin, quad = _soft_limit_params(HS, randomness)
        margin_eff = margin * (0.8 + 0.6 * ability_norm)
        lin_eff = lin * (1.0 - 0.6 * ability_norm)
        quad_eff = quad * (1.0 - 0.6 * ability_norm)
        over = np.maximum(0.0, distance - (HS + margin_eff))
        distance = distance - (lin_eff * over + quad_eff * over**2)

    # Dolna granica
    hs_val = float(HS) if HS is not None else 140.0
    if hs_val >= 200:
        min_frac = 0.10
    elif hs_val >= 101:
        min_frac = 0.18
    else:
        min_frac = 0.25
    lower_bound = (min_frac + 0.35 * ability_norm) * K
    distance = np.maximum(distance, lower_bound)

    # Punkty za odległość

    base_pts = 120.0 if float(K) >= 160.0 else 60.0
    distance_points = base_pts + (distance - K) * meter_value

    # Upadki
    over_k = np.maximum(0.0, distance - (K + 5))
    p_fall = np.clip(0.005 + 0.004 * over_k, 0.0, 0.25)
    fall = rng_loc.random(n) < p_fall

    # Styl – baza
    base_style = 17.3 + 0.010 * np.clip(distance - K, -30, 40) + 0.6 * (ability_norm - 0.5)
    soft_cap = 19.5
    base_style = soft_cap - (soft_cap - base_style) * 0.90

    # Telemark
    over_hard = np.maximum(0.0, distance - (K + 10))
    logits = -0.2 + 2.2 * (ability_norm - 0.5) - 0.05 * over_hard
    p_tele = 1.0 / (1.0 + np.exp(-logits))
    telemark = rng_loc.random(n) < p_tele
    no_tele = ~telemark

    no_tele_pen = np.where(no_tele, rng_loc.normal(0.7 + 0.002*np.maximum(0.0, distance-K),
                                                   0.18 + 0.08*randomness, size=n), 0.0)
    base_style = base_style - no_tele_pen

    over_hs = np.maximum(0.0, distance - HS) if HS is not None else np.zeros(n)
    hs_bonus = np.minimum(0.7, 0.045 * over_hs)
    tele_bonus = np.where(telemark, 0.45, 0.0)
    base_style_vec = base_style + hs_bonus + tele_bonus
    base_style_vec = np.asarray(base_style_vec, dtype=float)

    # Skorelowani sędziowie
    rho = np.clip(judges_rho, 0.0, 0.95)
    sigma = 0.22 + 0.06 * randomness
    cov = rho * np.ones((5, 5)) + (1 - rho) * np.eye(5)
    cov = cov * (sigma ** 2)

    judges = np.empty((n, 5))

    if fall.any():
        fall_center = np.clip(rng_loc.normal(11.6, 0.8, size=fall.sum()), 10.0, 13.2)
        for j in range(5):
            judges[fall, j] = np.clip(fall_center + rng_loc.normal(0.0, 0.40 + 0.1*randomness, size=fall.sum()), 10.0, 14.2)

    ok_mask = ~fall
    m = ok_mask.sum()
    if m > 0:
        Z = rng_loc.multivariate_normal(mean=np.zeros(5), cov=cov, size=m)
        scores = base_style_vec[ok_mask][:, None] + Z
        over_hs_ok = np.maximum(0.0, distance[ok_mask] - HS) if HS is not None else np.zeros(m)
        cap_hi = np.where((over_hs_ok > 0.0) & (telemark[ok_mask]), 19.9, 19.6)
        scores = np.clip(scores, 12.0, None)
        scores = np.minimum(scores, cap_hi[:, None])
        judges[ok_mask, :] = scores

    min_scores = judges.min(axis=1)
    max_scores = judges.max(axis=1)
    style_sum = judges.sum(axis=1) - min_scores - max_scores

    # NumPy sanity
    distance = np.asarray(distance, dtype=float)

    # Kompensacje
    wind_points = -8.0 * wind_flight
    gate_points = (gate_base - gate) * gate_points_per_step
    total_points = distance_points + style_sum + wind_points + gate_points

    distance_num = np.round(distance, 2)
    distance_str = np.array([f"{v:.2f}" for v in distance_num], dtype=object)
    if np.any(fall):
        distance_str[fall] = np.char.add(distance_str[fall].astype(str), "*")
    if np.any(bad_mask):
        distance_str[bad_mask] = np.char.add(distance_str[bad_mask].astype(str), "~")

    round_df = roster.copy().reset_index(drop=True)
    if "Upadek" in round_df.columns:
        round_df = round_df.drop(columns=["Upadek"])
    round_df["Upadek"] = fall.tolist()
    round_df["Gorszy najazd"] = bad_mask
    round_df["Wiatr (m/s) [flight]"] = np.round(wind_flight, 2)
    round_df["Wiatr (m/s) [takeoff]"] = np.round(wind_takeoff, 2)
    round_df["Odległość (m)"] = distance_num
    round_df["Odległość"] = distance_str
    round_df["Bramka"] = gate
    round_df["Sędzia1"] = np.round(judges[:, 0], 1)
    round_df["Sędzia2"] = np.round(judges[:, 1], 1)
    round_df["Sędzia3"] = np.round(judges[:, 2], 1)
    round_df["Sędzia4"] = np.round(judges[:, 3], 1)
    round_df["Sędzia5"] = np.round(judges[:, 4], 1)
    round_df["Odrzucona min"] = np.round(min_scores, 1)
    round_df["Odrzucona max"] = np.round(max_scores, 1)
    round_df["Noty stylowe"] = np.round(style_sum, 1)
    round_df["Punkty za odległość"] = np.round(distance_points, 1)
    round_df["Kompensacja wiatru"] = np.round(wind_points, 1)
    round_df["Kompensacja belki"] = np.round(gate_points, 1)
    round_df["Punkty rundy"] = np.round(total_points, 1)

    if sort_output:
        round_df = round_df.sort_values("Punkty rundy", ascending=False).reset_index(drop=True)
        round_df["Miejsce w rundzie"] = np.arange(1, n + 1)
    else:
        # zachowaj kolejność wejściową (np. pary KO); dodaj ranking punktowy bez sortowania
        round_df = round_df.reset_index(drop=True)
        round_df["Miejsce w rundzie"] = (-round_df["Punkty rundy"]).rank(method="min").astype(int)

    return round_df

def simulate_competition(
    roster: pd.DataFrame,
    round_cuts: list[int],
    K: int = 125,
    HS: int = 140,
    meter_value: float = None,
    wind_ms_mean: float = 0.0,
    wind_ms_sd: float = 0.8,
    gate_base: int = 10,
    gate_points_per_step: float = 4.0,
    p_gate_change: float = 0.06,
    max_gate_delta: int = 2,
    qual_spots: int = 50,
    rng: np.random.Generator | None = None,
    randomness: float = 0.35,
    elite_regress: float = 1.0,
    wind_phi: float = 0.75,
    wind_takeoff_gain: float = 0.5,
    wind_flight_gain: float = 2.2,
    judges_rho: float = 0.55,
):
    if meter_value is None:
        meter_value = compute_meter_value(K)

    # Qualifications
    kwal_df = simulate_round(
        roster, K, HS, meter_value, wind_ms_mean, wind_ms_sd,
        gate_base, gate_points_per_step, p_gate_change, max_gate_delta, rng,
        randomness=randomness, elite_regress=elite_regress,
        wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
        wind_flight_gain=wind_flight_gain, judges_rho=judges_rho
    )
    kwal_df.insert(0, "Runda", "Kwalifikacje")

    # KO qualification ranking (robust)
    # Build kval_rank safely even if column names vary ("Odległość" vs "Odległość (m)")
    _dist_col = "Odległość" if "Odległość" in kwal_df.columns else ("Odległość (m)" if "Odległość (m)" in kwal_df.columns else None)
    _cols = ["Zawodnik", "Kraj", "Punkty rundy"] + ([_dist_col] if _dist_col else [])
    try:
        _tmp = kwal_df[_cols].copy()
    except Exception:
        _tmp = kwal_df[["Zawodnik", "Kraj", "Punkty rundy"]].copy()
        _dist_col = None
    _rename_map = {"Punkty rundy": "Punkty"}
    if _dist_col:
        _rename_map[_dist_col] = "Odl.Q"
    kval_rank = _tmp.rename(columns=_rename_map)

    # KO50 kwalifikacje: kolejność do wyświetlenia: Punkty ↓, a w remisie Odl.Q ↓
    kval_rank["Punkty"] = pd.to_numeric(kval_rank["Punkty"], errors="coerce").round(1)
    if "Odl.Q" in kval_rank.columns:
        kval_rank["_OdlQ_sort"] = pd.to_numeric(kval_rank["Odl.Q"], errors="coerce").fillna(-1e9)
    else:
        kval_rank["_OdlQ_sort"] = -1e9

    kval_rank = (
        kval_rank
        .sort_values(["Punkty","_OdlQ_sort"], ascending=[False, False], kind="mergesort")
        .reset_index(drop=True)
    )

    # Ex aequo: ci sami „Punkty” → to samo „Miejsce” (1,1,3…)
    try:
        kval_rank["__pos"] = np.arange(1, len(kval_rank)+1)
        kval_rank["Miejsce"] = kval_rank.groupby(["Punkty"])["__pos"].transform("min").astype(int)
        kval_rank.drop(columns=["__pos","_OdlQ_sort"], inplace=True, errors="ignore")
        _desired = ["Miejsce", "Zawodnik", "Kraj", "Odl.Q", "Punkty"]
        kval_rank = kval_rank.reindex(columns=[c for c in _desired if c in kval_rank.columns])
    except Exception:
        kval_rank = _apply_tied_places(kval_rank, points_col="Punkty", place_col="Miejsce", ascending=False, decimals=1)
    if not isinstance(kval_rank, pd.DataFrame):
        kval_rank = pd.DataFrame(columns=["Miejsce","Zawodnik","Kraj","Punkty","Odl.Q"])
    # Into contest
    qmask = pd.to_numeric(kval_rank.get("Miejsce"), errors="coerce") <= int(qual_spots)
    qualified = (
        kval_rank.loc[qmask]
        .merge(kwal_df[["Zawodnik","UM","Forma"]], on="Zawodnik", how="left")
        [["Zawodnik","UM","Forma","Kraj"]]
        .reset_index(drop=True)
    )

    all_rounds = []
    prev_df = None

    for idx, cut in enumerate(round_cuts, start=1):
        if idx == 1:
            field = qualified.copy()  # R1: bierz całą listę, także ex aequo na 50.
        else:
            field = (prev_df.sort_values("Punkty rundy", ascending=False)
                    .head(min(int(cut), len(prev_df)))
                    [["Zawodnik","UM","Forma","Kraj"]]
                    .reset_index(drop=True))

        if len(field) == 0:
            break

        rnd_df = simulate_round(
            field, K, HS, meter_value, wind_ms_mean, wind_ms_sd,
            gate_base, gate_points_per_step, p_gate_change, max_gate_delta, rng,
            randomness=randomness, elite_regress=elite_regress,
            wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
            wind_flight_gain=wind_flight_gain, judges_rho=judges_rho
        )
        rnd_df.insert(0, "Runda", idx)
        all_rounds.append(rnd_df)
        prev_df = rnd_df.copy()

    contest_results = pd.concat(all_rounds, ignore_index=True) if all_rounds else pd.DataFrame()

    if not contest_results.empty:
        points = (
            contest_results.groupby(["Zawodnik", "Kraj"], as_index=False)["Punkty rundy"]
            .sum()
            .rename(columns={"Punkty rundy": "Punkty"})
        )
        klasyf = points.copy()
        for idx in range(1, len(all_rounds)+1):
            dist_i = contest_results[contest_results["Runda"] == idx][["Zawodnik","Odległość"]].rename(columns={"Odległość": f"Odl.{idx}"})
            klasyf = klasyf.merge(dist_i, on="Zawodnik", how="left")

            # --- porządek i miejsca: najpierw punkty, a przy remisie po odległości z tej rundy ---
            klasyf["Punkty"] = pd.to_numeric(klasyf["Punkty"], errors="coerce").round(1)

            # bieżąca kolumna z odległością tej rundy, np. "Odl.1", "Odl.2", ...
            _dist_col = f"Odl.{idx}"
            _tie_dist = pd.to_numeric(
                klasyf.get(_dist_col, "")
                    .astype(str)
                    .str.replace("*","", regex=False)
                    .str.replace("~","", regex=False)
                    .str.replace(",", ".", regex=False),
                errors="coerce"
            ).fillna(-1e9)

            # kolejność do wyświetlenia: Punkty ↓, w remisie Odl.idx ↓
            klasyf = (
                klasyf
                .assign(__tie_dist=_tie_dist)
                .sort_values(["Punkty", "__tie_dist"], ascending=[False, False], kind="mergesort")
                .drop(columns="__tie_dist")
                .reset_index(drop=True)
            )

            # miejsca ex aequo (1,1,3…)
            klasyf = _apply_tied_places(klasyf, points_col="Punkty", place_col="Miejsce", ascending=False, decimals=1)
            klasyf["Punkty FIS"] = _fis_points_for_place(klasyf["Miejsce"])
            # utrzymanie kolejności kolumn (Punkty FIS na końcu)
            cols = list(klasyf.columns)
            if "Punkty FIS" in cols:
                cols = [c for c in cols if c != "Punkty FIS"] + ["Punkty FIS"]
                klasyf = klasyf[cols]
            # --- enforce desired column order for final "Klasyfikacja" ---
            try:
                import re as _re_
                odl_cols = [c for c in klasyf.columns if _re_.match(r"^Odl\.\d+$", str(c))]
                try:
                    odl_cols = sorted(odl_cols, key=lambda x: int(str(x).split(".")[1]))
                except Exception:
                    odl_cols = sorted(odl_cols)
                desired = ["Miejsce", "Zawodnik", "Kraj"] + odl_cols + ["Punkty", "Punkty FIS"]
                tail = [c for c in klasyf.columns if c not in desired]
                ordered = [c for c in desired if c in klasyf.columns] + tail
                klasyf = klasyf[ordered]
            except Exception:
                pass


    else:
        klasyf = pd.DataFrame(columns=["Miejsce","Zawodnik","Kraj","Punkty"])

    return kwal_df, kval_rank, contest_results, klasyf

# ---------- KO MODE (Turniej 4 Skoczni) ----------

def _pair_indices_for_ko(n: int):
    """Qualification-based edge pairing (T4S standard).
    Pair 1: 1 vs 50 (indices 0 vs n-1), then 2 vs 49, ..., 25 vs 26.
    """
    return [(i, n-1-i) for i in range(n//2)]

def simulate_ko_competition(
    roster: pd.DataFrame,
    K: int = 125,
    HS: int = 140,
    meter_value: float = None,
    qual_spots: int = 50,
    wind_ms_mean: float = 0.0,
    wind_ms_sd: float = 0.8,
    gate_base: int = 10,
    gate_points_per_step: float = 4.0,
    p_gate_change: float = 0.06,
    max_gate_delta: int = 2,
    rng: np.random.Generator | None = None,
    randomness: float = 0.35,
    elite_regress: float = 1.0,
    wind_phi: float = 0.75,
    wind_takeoff_gain: float = 0.5,
    wind_flight_gain: float = 2.2,
    judges_rho: float = 0.55,
):
    if meter_value is None:
        meter_value = compute_meter_value(K)

    # Kwalifikacje
    kwal_df = simulate_round(
        roster=roster, K=K, HS=HS, meter_value=meter_value,
        wind_ms_mean=wind_ms_mean, wind_ms_sd=wind_ms_sd,
        gate_base=gate_base, gate_points_per_step=gate_points_per_step,
        p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
        rng=rng, randomness=randomness, elite_regress=elite_regress,
        wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
        wind_flight_gain=wind_flight_gain, judges_rho=judges_rho
    )
    kwal_df.insert(0, "Runda", "Kwalifikacje")

    # KO qualification ranking (robust)
    # Build kval_rank safely even if column names vary ("Odległość" vs "Odległość (m)")
    _dist_col = "Odległość" if "Odległość" in kwal_df.columns else ("Odległość (m)" if "Odległość (m)" in kwal_df.columns else None)
    _cols = ["Zawodnik", "Kraj", "Punkty rundy"] + ([_dist_col] if _dist_col else [])
    try:
        _tmp = kwal_df[_cols].copy()
    except Exception:
        _tmp = kwal_df[["Zawodnik", "Kraj", "Punkty rundy"]].copy()
        _dist_col = None
    _rename_map = {"Punkty rundy": "Punkty"}
    if _dist_col:
        _rename_map[_dist_col] = "Odl.Q"
    kval_rank = _tmp.rename(columns=_rename_map)

    # KO50 kwalifikacje: Punkty ↓, a w remisie Odl.Q ↓; „Miejsce” wspólne (1,1,3…)
    kval_rank["Punkty"] = pd.to_numeric(kval_rank["Punkty"], errors="coerce").round(1)
    kval_rank["_OdlQ_sort"] = pd.to_numeric(kval_rank.get("Odl.Q"), errors="coerce").fillna(-1e9)

    kval_rank = (
        kval_rank
        .sort_values(["Punkty", "_OdlQ_sort"], ascending=[False, False], kind="mergesort")
        .reset_index(drop=True)
    )

    # wspólne „Miejsce” dla tych samych „Punkty”
    kval_rank["__pos"] = np.arange(1, len(kval_rank)+1)
    kval_rank["Miejsce"] = kval_rank.groupby("Punkty")["__pos"].transform("min").astype(int)
    kval_rank.drop(columns=["__pos", "_OdlQ_sort"], inplace=True, errors="ignore")
    _desired = ["Miejsce", "Zawodnik", "Kraj", "Odl.Q", "Punkty"]
    kval_rank = kval_rank.reindex(columns=[c for c in _desired if c in kval_rank.columns])

    if not isinstance(kval_rank, pd.DataFrame):
        kval_rank = pd.DataFrame(columns=["Miejsce","Zawodnik","Kraj","Punkty","Odl.Q"])
    N = min(int(qual_spots), len(kval_rank))
    # KO wymaga par, więc liczba musi być parzysta
    if N % 2 == 1:
        N -= 1
    ko_field = kval_rank.head(N).copy().reset_index(drop=True)

    # Parowanie KO
    pairs = _pair_indices_for_ko(N)
    order_idx = [idx for pair in pairs for idx in pair]
    field_ko = ko_field.iloc[order_idx][["Zawodnik","Kraj"]].merge(
        roster[["Zawodnik","UM","Forma","Kraj"]], on=["Zawodnik","Kraj"], how="left"
    ).reset_index(drop=True)

    # Runda KO (I)
    r1 = simulate_round(
        roster=field_ko, K=K, HS=HS, meter_value=meter_value,
        wind_ms_mean=wind_ms_mean, wind_ms_sd=wind_ms_sd,
        gate_base=gate_base, gate_points_per_step=gate_points_per_step,
        p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
        rng=rng, randomness=randomness, elite_regress=elite_regress,
        wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
        wind_flight_gain=wind_flight_gain, judges_rho=judges_rho
    , sort_output=False)
    r1.insert(0, "Runda", 1)

    # Wyniki par
    winners = []
    losers = []
    for pidx, (i, j) in enumerate(pairs, start=1):
        a = r1.iloc[2*(pidx-1)]
        b = r1.iloc[2*(pidx-1) + 1]
        if a["Punkty rundy"] >= b["Punkty rundy"]:
            winners.append(a); losers.append(b)
        else:
            winners.append(b); losers.append(a)

    winners_df = pd.DataFrame(winners).reset_index(drop=True)
    losers_df  = pd.DataFrame(losers).reset_index(drop=True)

    # Lucky Losers (dopełnienie do 30)
    need = max(0, 30 - len(winners_df))
    losers_sorted = losers_df.sort_values("Punkty rundy", ascending=False).reset_index(drop=True)
    ll_names = set(losers_sorted.head(need)["Zawodnik"]) if need > 0 else set()

    finalists = pd.concat([winners_df, losers_sorted.head(need)], ignore_index=True)
    finalists = finalists.sort_values("Punkty rundy", ascending=False).reset_index(drop=True)
    finalists_field = finalists[["Zawodnik","UM","Forma","Kraj"]].reset_index(drop=True)

    # Runda finałowa (II)
    r2 = simulate_round(
        roster=finalists_field, K=K, HS=HS, meter_value=meter_value,
        wind_ms_mean=wind_ms_mean, wind_ms_sd=wind_ms_sd,
        gate_base=gate_base, gate_points_per_step=gate_points_per_step,
        p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
        rng=rng, randomness=randomness, elite_regress=elite_regress,
        wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
        wind_flight_gain=wind_flight_gain, judges_rho=judges_rho
    )
    r2.insert(0, "Runda", 2)

    # Klasyfikacja końcowa (suma pkt)
    all_rounds = pd.concat([r1, r2], ignore_index=True)
    points = all_rounds.groupby(["Zawodnik","Kraj"], as_index=False)["Punkty rundy"].sum().rename(columns={"Punkty rundy":"Punkty"})
    klasyf = points.merge(
        r1[["Zawodnik","Odległość"]].rename(columns={"Odległość":"Odl.1"}), on="Zawodnik", how="left"
    ).merge(
        r2[["Zawodnik","Odległość"]].rename(columns={"Odległość":"Odl.2"}), on="Zawodnik", how="left"
    )
    d2 = pd.to_numeric(
        klasyf.get("Odl.2","").astype(str)
            .str.replace("*","", regex=False)
            .str.replace("~","", regex=False)
            .str.replace(",", ".", regex=False),
        errors="coerce"
    ).fillna(-1e9)

    d1 = pd.to_numeric(
        klasyf.get("Odl.1","").astype(str)
            .str.replace("*","", regex=False)
            .str.replace("~","", regex=False)
            .str.replace(",", ".", regex=False),
        errors="coerce"
    ).fillna(-1e9)

    klasyf = (
        klasyf
        .assign(__d2=d2, __d1=d1)
        .sort_values(["Punkty","__d2","__d1"], ascending=[False, False, False], kind="mergesort")
        .drop(columns=["__d2","__d1"])
        .reset_index(drop=True)
    )

    # miejsca ex aequo: ci sami „Punkty” = to samo „Miejsce” (1,1,3…)
    klasyf["Punkty"] = pd.to_numeric(klasyf["Punkty"], errors="coerce").round(1)
    klasyf = _apply_tied_places(klasyf, points_col="Punkty", place_col="Miejsce", ascending=False, decimals=1)
    klasyf["Punkty FIS"] = _fis_points_for_place(klasyf["Miejsce"])
    cols = list(klasyf.columns)
    if "Punkty FIS" in cols:
        cols = [c for c in cols if c != "Punkty FIS"] + ["Punkty FIS"]
        klasyf = klasyf[cols]
    # --- enforce desired column order for KO50 final "Klasyfikacja" ---
    try:
        desired = ["Miejsce", "Zawodnik", "Kraj"]
        # dołącz odległości w kolejności rosnącej numeru
        import re as _re_
        odl_cols = [c for c in klasyf.columns if _re_.match(r"^Odl\.[0-9]+$", str(c))]
        try:
            odl_cols = sorted(odl_cols, key=lambda x: int(str(x).split(".")[1]))
        except Exception:
            odl_cols = sorted(odl_cols)
        desired = desired + odl_cols + ["Punkty", "Punkty FIS"]
        tail = [c for c in klasyf.columns if c not in desired]
        klasyf = klasyf[[c for c in desired if c in klasyf.columns] + tail]
    except Exception:
        pass

    # Zbiorcze "Konkurs - rundy"
    contest_rows = pd.concat([r1, r2], ignore_index=True)
    contest_rows = contest_rows.sort_values(["Runda","Punkty rundy"], ascending=[True, False]).reset_index(drop=True)

    # KO – Pary (R1): para, zawodnik, kraj, odległość, punkty, status
    pairs_info = []
    win_names = set(winners_df["Zawodnik"])
    for pidx, (i, j) in enumerate(pairs, start=1):
        a_idx = 2*(pidx-1); b_idx = a_idx+1
        row_a = r1.iloc[a_idx].copy(); row_b = r1.iloc[b_idx].copy()
        row_a["Para"] = pidx; row_b["Para"] = pidx

        def _status(name: str) -> str:
            if name in win_names:
                return "Z pary"
            return "Lucky Loser" if name in ll_names else "Odpada"

        row_a["Status"] = _status(row_a["Zawodnik"])
        row_b["Status"] = _status(row_b["Zawodnik"])
        pairs_info.append(row_a); pairs_info.append(row_b)

    ko_pairs_sheet = pd.DataFrame(pairs_info).reset_index(drop=True)
    ko_pairs_sheet = ko_pairs_sheet[
        ["Para","Zawodnik","Kraj","Odległość","Punkty rundy","Status"] +
        [c for c in r1.columns if c.startswith("Sędzia")]
    ]

    # KO – Lucky Losers
    ll_sheet = losers_sorted.copy()
    ll_sheet.insert(0, "LL", ll_sheet["Zawodnik"].isin(ll_names))
    ll_sheet.rename(columns={"Punkty rundy":"Punkty R1","Odległość":"Odl.1"}, inplace=True)

    extra_sheets = {
        "KO - Pary (R1)": ko_pairs_sheet,
        "KO - Lucky Losers": ll_sheet,
    }

    return kwal_df, kval_rank, contest_rows, klasyf, extra_sheets

def simulate_ko_single_elim(
    roster: pd.DataFrame,
    K: int = 125,
    HS: int = 140,
    meter_value: float = None,
    bracket_size: int = 64,
    wind_ms_mean: float = 0.0,
    wind_ms_sd: float = 0.8,
    gate_base: int = 10,
    gate_points_per_step: float = 4.0,
    p_gate_change: float = 0.06,
    max_gate_delta: int = 2,
    rng: np.random.Generator | None = None,
    randomness: float = 0.35,
    elite_regress: float = 1.0,
    wind_phi: float = 0.75,
    wind_takeoff_gain: float = 0.5,
    wind_flight_gain: float = 2.2,
    judges_rho: float = 0.55,
):
    """
    Tryb: czysta drabinka single-elimination bez Lucky Losers.
    Kwalifikacje → TOP `bracket_size` → pary (1-64, 2-63, ...) → 32 → 16 → 8 → 4 → 2 (finał).
    Klasyfikacja na podstawie sumy punktów ze wszystkich rund danego zawodnika.
    """
    if meter_value is None:
        meter_value = compute_meter_value(K)

    # Kwalifikacje (wszyscy)
    kwal_df = simulate_round(
        roster=roster, K=K, HS=HS, meter_value=meter_value,
        wind_ms_mean=wind_ms_mean, wind_ms_sd=wind_ms_sd,
        gate_base=gate_base, gate_points_per_step=gate_points_per_step,
        p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
        rng=rng, randomness=randomness, elite_regress=elite_regress,
        wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
        wind_flight_gain=wind_flight_gain, judges_rho=judges_rho
    )
    kwal_df.insert(0, "Runda", "Kwalifikacje")
    kval_rank = kwal_df[["Zawodnik","Kraj","Punkty rundy","Odległość"]].rename(columns={"Punkty rundy":"Punkty","Odległość":"Odl.Q"})
    kval_rank = kval_rank.sort_values("Punkty", ascending=False).reset_index(drop=True)
    # Ex aequo w kwalifikacjach KO (spójnie z klasykiem)
    kval_rank = _apply_tied_places(kval_rank, points_col="Punkty", place_col="Miejsce", ascending=False, decimals=1)

    N = min(int(bracket_size), len(kval_rank))
    # Wymuś potęgę dwójki
    pow2 = 1 << (N.bit_length()-1)
    if pow2 != N:
        N = pow2  # zejście do najbliższej mniejszej potęgi 2
    if N < 2:
        raise ValueError("Za małe pole zawodów do KO single-elim")

    # Pole KO wg kwalifikacji
    ko_field = kval_rank.head(N).copy().reset_index(drop=True)

    # R1 pary 1-64, 2-63, ...
    pairs = _pair_indices_for_ko(N)
    order_idx = [idx for pair in pairs for idx in pair]
    field_r = ko_field.iloc[order_idx][["Zawodnik","Kraj"]].merge(
        roster[["Zawodnik","UM","Forma","Kraj"]], on=["Zawodnik","Kraj"], how="left"
    ).reset_index(drop=True)

    rounds = []
    round_no = 1
    contestants = field_r.copy()

    extra_sheets = {}

    while len(contestants) >= 2:
        # Parowanie obecnej rundy: w kolejności aktualnego ułożenia (2 kolejne osoby = para)
        # Zakładamy, że na wejściu R1 mamy seeding 1-64,2-63 itd., a dalej zwykły bracket.
        r_df = simulate_round(
            roster=contestants, K=K, HS=HS, meter_value=meter_value,
            wind_ms_mean=wind_ms_mean, wind_ms_sd=wind_ms_sd,
            gate_base=gate_base, gate_points_per_step=gate_points_per_step,
            p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
            rng=rng, randomness=randomness, elite_regress=elite_regress,
            wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
            wind_flight_gain=wind_flight_gain, judges_rho=judges_rho,
            sort_output=False
        )
        r_df.insert(0, "Runda", round_no)

        # Wyznacz zwycięzców i przegranych parami
        winners = []
        losers = []
        for pidx in range(0, len(r_df), 2):
            a = r_df.iloc[pidx]
            b = r_df.iloc[pidx+1]
            if a["Punkty rundy"] >= b["Punkty rundy"]:
                winners.append(a); losers.append(b)
            else:
                winners.append(b); losers.append(a)

        # Zapamiętaj pary w arkuszu pomocniczym
        pairs_info = []
        for pnum in range(len(r_df)//2):
            a = r_df.iloc[2*pnum].copy()
            b = r_df.iloc[2*pnum+1].copy()
            a["Para"] = pnum+1; b["Para"] = pnum+1
            win_names = set(pd.DataFrame(winners)["Zawodnik"])
            a["Status"] = "Wygrany" if a["Zawodnik"] in win_names else "Odpada"
            b["Status"] = "Wygrany" if b["Zawodnik"] in win_names else "Odpada"
            pairs_info.append(a); pairs_info.append(b)

        extra_sheets[f"KO{len(contestants)} - Pary (R{round_no})"] = pd.DataFrame(pairs_info)[
            ["Para","Zawodnik","Kraj","Odległość","Punkty rundy","Status"] +
            [c for c in r_df.columns if c.startswith("Sędzia")]
        ].reset_index(drop=True)

        rounds.append(r_df)
        # Ułóż zwycięzców w kolejności dla następnej rundy
        winners_df = pd.DataFrame(winners).reset_index(drop=True)
        contestants = winners_df[["Zawodnik","Kraj"]].merge(
            roster[["Zawodnik","UM","Forma","Kraj"]], on=["Zawodnik","Kraj"], how="left"
        ).reset_index(drop=True)
        round_no += 1

    # Zbiorczy DF rund
    contest_rows = pd.concat(rounds, ignore_index=True)
    contest_rows = contest_rows.sort_values(["Runda", "Punkty rundy"], ascending=[True, False]).reset_index(drop=True)

    # Klasyfikacja: suma punktów z rund; dogrywka kolejności przez najwyższą rundę osiągniętą
    all_points = contest_rows.groupby(["Zawodnik","Kraj"], as_index=False)["Punkty rundy"].sum().rename(columns={"Punkty rundy":"Punkty"})
    max_round = contest_rows.groupby(["Zawodnik","Kraj"], as_index=False)["Runda"].max().rename(columns={"Runda":"MaxRunda"})
    klasyf = all_points.merge(max_round, on=["Zawodnik","Kraj"], how="left")
    # Najpierw kto dalej zaszedł, potem punkty
    klasyf["EtapRank"] = -klasyf["MaxRunda"]
    klasyf = klasyf.sort_values(["EtapRank","Punkty"], ascending=[True, False]).reset_index(drop=True)
    # Dodaj kolumny odległości z 1. i ostatniej rundy (podgląd)
    try:
        first_round = contest_rows[contest_rows["Runda"]==1][["Zawodnik","Odległość"]].rename(columns={"Odległość":"Odl.1"})
        last_round_idx = contest_rows["Runda"].max()
        last_round = contest_rows[contest_rows["Runda"]==last_round_idx][["Zawodnik","Odległość"]].rename(columns={"Odległość":f"Odl.{last_round_idx}"})
        klasyf = klasyf.merge(first_round, on="Zawodnik", how="left").merge(last_round, on="Zawodnik", how="left")
    except Exception:
        pass
    # Tied places dla klasyfikacji KO (1,1,3...)
    klasyf = klasyf.sort_values("Punkty", ascending=False, kind="stable").reset_index(drop=True)
    klasyf.insert(0, "Miejsce", (-klasyf["Punkty"]).rank(method="min").astype(int))
    klasyf.drop(columns=["EtapRank"], inplace=True)

    return kwal_df, kval_rank, contest_rows, klasyf, extra_sheets



def _csv_safe_text(s: str) -> str:
    if s is None:
        return ""
    try:
        s = str(s)
    except Exception:
        s = repr(s)
    return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", s)

def _write_csv(df, path: Path):
    import csv
    df2 = _sanitize_df_SAFE3(df)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([_csv_safe_text(c) for c in df2.columns])
        for _, row in df2.iterrows():
            w.writerow([_csv_safe_text(v) for v in row.tolist()])


# --- DEFENSIVE STUB: ensure _sanitize_df_SAFE3 exists ---
try:
    _sanitize_df_SAFE3
except NameError:
    def _sanitize_df_SAFE3(df) -> pd.DataFrame:
        import numpy as np
        if df is None:
            return pd.DataFrame()
        try:
            out = pd.DataFrame(df).copy()
        except Exception:
            return pd.DataFrame()
        return out.replace([np.inf, -np.inf], np.nan)
# --------------------------------------------------------


    def _reorder_points_after_distances(df):
        import re as _re
        import pandas as pd
        if not isinstance(df, pd.DataFrame) or df.empty:
            return df

        cols = list(df.columns)
        if "Punkty" not in cols:
            return df

        fis_col = "Punkty FIS"
        dist_cols = [c for c in cols if (_re.match(r"^Odl(\.|[1-6])", str(c)) or "Odległość" in str(c) or "Odl.Q" in str(c))]

        # wszystko poza odległościami i punktami (oraz Punkty FIS) -> prefix
        prefix = [c for c in cols if c not in dist_cols + ["Punkty", fis_col]]

        # ogon: najpierw Punkty, a jeśli jest, to na samym końcu Punkty FIS
        tail = ["Punkty"] + ([fis_col] if fis_col in cols else [])

        ordered = prefix + dist_cols + tail
        ordered = [c for c in ordered if c in cols]
        try:
            return df[ordered].copy()
        except Exception:
            return df

    
def _insert_flags_xlsx(writer, sheet_name: str, df, kraj_col="Kraj", flag_dir=FLAGS_DIR):
    """Wstawia 18x11 PNG obok kodu kraju w kolumnie 'Kraj'."""
    try:
        # 🔧 AKTUALIZACJA: zawsze traktuj flag_dir jak Path (obsłuży też string)
        flag_dir = Path(flag_dir)
        if not flag_dir.is_absolute():
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            flag_dir = (base / flag_dir).resolve()

        if df is None or getattr(df, "empty", True):
            return
        if kraj_col not in df.columns:
            return

        wb = writer.book
        ws = writer.sheets[sheet_name]
        col_idx = df.columns.get_loc(kraj_col)

        fmt = wb.add_format({"indent": 3, "valign": "vcenter"})
        ws.set_column(col_idx, col_idx, 14, fmt)

        inserted = 0
        for r, code in enumerate(df[kraj_col].astype(str), start=1):  # 1 = pomiń nagłówek
            p = flag_dir / f"{code.strip().lower()}.png"
            if p.exists():
                ws.insert_image(r, col_idx, str(p), {
                    "x_offset": 2,
                    "y_offset": 1,
                    "object_position": 1,
                })
                inserted += 1

        # 👇 pomocny komunikat diagnostyczny (możesz usunąć po testach)
        print(f"[flags] {sheet_name}: {inserted} wstawionych z {flag_dir}")
    except Exception as e:
        # 👇 na czas testów warto widzieć błąd
        print(f"[flags] {sheet_name}: pominięto ({e})")

def save_to_excel(
    roster: pd.DataFrame,
    qual_df: pd.DataFrame,
    kval_rank: pd.DataFrame,
    contest_rows: pd.DataFrame,
    klasyf: pd.DataFrame,
    outdir: Path,
    hill_name: str,
    extra_sheets: dict | None = None,
) -> Path:
    # --- Local fallbacks to avoid NameError ---
    def _sheet_name_local(name: str, used_names: set[str]) -> str:
        try:
            # try global helper if present
            return _safe_sheet_name(name, used_names)  # type: ignore[name-defined]
        except Exception:
            import re
            base = re.sub(r'[:\\/*?\\[\\]]', "_", str(name)).strip() or "Sheet"
            base = base[:31]
            cand = base
            i = 1
            while cand in used_names:
                suffix = f"_{i}"
                cand = (base[: max(0, 31 - len(suffix))] + suffix) or f"Sheet_{i}"
                i += 1
            used_names.add(cand)
            return cand

    
    def _sanitize_df_STRONG(df) -> pd.DataFrame:
        try:
            return _sanitize_df_SAFE3(df)  # type: ignore[name-defined]
        except Exception:
            import numpy as np, math as _math, re as _re
            if df is None:
                return pd.DataFrame()
            try:
                out = pd.DataFrame(df).copy()
            except Exception:
                return pd.DataFrame()

            # Clean column names from control chars
            clean_cols = []
            for c in out.columns:
                cs = _re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", str(c))
                clean_cols.append(cs)
            out.columns = clean_cols

            # Replace inf/-inf
            out = out.replace([np.inf, -np.inf], np.nan)

            # Serialize object dtype and clean strings
            for c in out.columns:
                if pd.api.types.is_object_dtype(out[c]):
                    def _clean(x):
                        if x is None:
                            return ""
                        try:
                            if isinstance(x, float) and _math.isnan(x):
                                return ""
                        except Exception:
                            pass
                        if isinstance(x, (list, dict, set, tuple)):
                            x = str(x)
                        s = str(x)
                        s = _re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", s)
                        return s
                    out[c] = out[c].map(_clean)
            return out


    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = (hill_name or "Skocznia").strip().replace("/", "-").replace("\\\\", "-")
    outpath = outdir / f"{safe_name}_{ts}.xlsx"

    # --- DEBUG: zapisz mapę kolejności arkuszy (pomaga znaleźć sheet6.xml) ---
    try:
        order_map = []
        i = 1
        for nm in list(base_sheets.keys()):
            order_map.append((i, nm))
            i += 1
        if isinstance(extra_sheets, dict):
            for k, _ in sorted(extra_sheets.items(), key=lambda kv: str(kv[0])):
                order_map.append((i, str(k)))
                i += 1
        dbg = outdir / f"{safe_name}_{ts}_sheet_order.txt"
        with open(dbg, "w", encoding="utf-8") as fh:
            fh.write("\n".join([f"{idx}: {nm}" for idx, nm in order_map]))
    except Exception:
        pass
    # -------------------------------------------------------------------------

    used_names: set[str] = set()

    base_sheets = {
        "Zawodnicy": _sanitize_df_STRONG(roster),
        "Kwalifikacje - rundy": _sanitize_df_STRONG(qual_df),
        "Klasyfikacja kwal.": _sanitize_df_STRONG(_reorder_points_after_distances(kval_rank)),
        "Konkurs - rundy": _sanitize_df_STRONG(contest_rows),
        "Klasyfikacja": _sanitize_df_STRONG(_reorder_points_after_distances(klasyf)),
    }

    csv_written = []

    with pd.ExcelWriter(
        outpath,
        engine="xlsxwriter",
        engine_kwargs={"options": {"strings_to_urls": False, "strings_to_formulas": False, "nan_inf_to_errors": True}},
    ) as writer:
        for name, df in base_sheets.items():
            sheet = _sheet_name_local(name, used_names)
            df.to_excel(writer, index=False, sheet_name=sheet)
            _insert_flags_xlsx(writer, sheet, df, flag_dir="./flags", kraj_col="Kraj")  # ← OK

        if isinstance(extra_sheets, dict):
            for k, v in sorted(extra_sheets.items(), key=lambda kv: str(kv[0])):
                try:
                    df_extra = v if isinstance(v, pd.DataFrame) else pd.DataFrame(v)
                except Exception:
                    continue
                df_extra = _sanitize_df_STRONG(df_extra)
                sheet = _sheet_name_local(str(k), used_names)
                df_extra.to_excel(writer, index=False, sheet_name=sheet)

                # DODAJ TĘ LINIĘ TUŻ PO to_excel:
                _insert_flags_xlsx(writer, sheet, df_extra, flag_dir="./flags", kraj_col="Kraj")  # ← DODAĆ

                # (opcjonalnie, jeśli masz w niektórych arkuszach wiele kolumn "Kraj*"):
                # for col in [c for c in df_extra.columns if c.lower().startswith("kraj")]:
                #     _insert_flags_xlsx(writer, sheet, df_extra, flag_dir="./flags", kraj_col=col)

                # Highlight winners for KO64 per-row drabinka (xlsxwriter)
                try:
                    if str(k) == "KO64 - Drabinka" and isinstance(df_extra, pd.DataFrame) and not df_extra.empty:
                        ws = writer.sheets.get(sheet)
                        if ws is not None and "Wygrana" in list(df_extra.columns):
                            fmt_ok = writer.book.add_format({"bold": True, "bg_color": "#D9FDD3"})
                            wy_idx = list(df_extra.columns).index("Wygrana")
                            for i, val in enumerate(df_extra.iloc[:, wy_idx].astype(str).tolist()):
                                if val in ("✓", "True", "1"):
                                    ws.set_row(i+1, None, fmt_ok)  # +1: skip header row
                except Exception:
                    pass

                nm = str(k).replace(" ", "_").replace("/", "-")
                csv_dir = outdir / "csv"
                csv_dir.mkdir(parents=True, exist_ok=True)
                csv_path = csv_dir / f"{safe_name}_{ts}_{nm}.csv"
                try:
                    _write_csv(df_extra, csv_path)
                except Exception:
                    pass
                else:
                    csv_written.append(csv_path)

    if csv_written:
        print("Dodatkowe arkusze zapisane również jako CSV:")
        for pth in csv_written:
            print("  -", pth)

    return outpath


def main():
    p = argparse.ArgumentParser(description="Symulator skoków narciarskich (v6: klasyczny + KO; AR(1), split wiatru, skorelowani sędziowie, płynny elite-regress)")
    p.add_argument("--excel", default=DEFAULT_EXCEL, help="Ścieżka do pliku Excel z zawodnikami")
    p.add_argument("--hill-name", default="Zakopane", help="Nazwa skoczni (do nazwy pliku)")
    p.add_argument("--k", type=int, default=125, help="Punkt K")
    p.add_argument("--hs", type=int, default=140, help="HS")
    p.add_argument("--meter", type=float, default=None, help="Punkty za metr (domyślnie wg K)")
    p.add_argument("--wind-mean", type=float, default=0.0, help="Średni wiatr (m/s)")
    p.add_argument("--wind-sd", type=float, default=0.8, help="Odchylenie wiatru (m/s)")
    p.add_argument("--wind-phi", type=float, default=0.75, help="Autokorelacja wiatru AR(1) [0..0.95]")
    p.add_argument("--wind-takeoff-gain", type=float, default=0.5, help="Wpływ wiatru na progu (metry / m/s)")
    p.add_argument("--wind-flight-gain", type=float, default=2.2, help="Wpływ wiatru w locie (metry / m/s)")
    p.add_argument("--gate", type=int, default=10, help="Belka bazowa")
    p.add_argument("--outdir", default=DEFAULT_OUTDIR, help="Katalog docelowy na wyniki XLSX")
    p.add_argument("--randomness", type=float, default=0.35, help="Dowolna wartość (może być >1.0) – większa = większa losowość")
    p.add_argument("--elite-regress", type=float, default=1.0, help=">=0 – płynnie działa dla ability_norm 0.80..1.00")
    p.add_argument("--p-gate-change", type=float, default=0.06, help="Prawdopodobieństwo zmiany belki dla zawodnika")
    p.add_argument("--max-gate-delta", type=int, default=2, help="Maksymalna zmiana belki ±")
    p.add_argument("--judges-rho", type=float, default=0.55, help="Docelowa korelacja not sędziów [0..0.95]")
    p.add_argument("--qual-spots", type=int, default=50, help="Ilu przechodzi z kwalifikacji do konkursu / KO")
    p.add_argument("--round-cuts", default="50,30", help='Lista cięć (tryb klasyczny), np. "40,30,30,30"')

    p.add_argument("--ko-bracket", type=int, default=None, help="Single-elimination KO bez Lucky Losers; rozmiar drabinki (np. 64)")
    p.add_argument("--ko", action="store_true", help="Użyj systemu KO (Turniej 4 Skoczni) zamiast klasycznych cięć")

    args = p.parse_args()

    excel_path = Path(args.excel)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    randomness = float(args.randomness)  # może być > 1.0
    elite_regress = float(max(0.0, args.elite_regress))
    wind_phi = float(np.clip(args.wind_phi, 0.0, 0.95))
    judges_rho = float(np.clip(args.judges_rho, 0.0, 0.95))
    p_gate_change = float(np.clip(args.p_gate_change, 0.0, 1.0))
    max_gate_delta = int(args.max_gate_delta)

    print(f"→ Wczytuję zawodników z: {excel_path.resolve() if excel_path.exists() else excel_path}")
    roster = load_roster(excel_path)
    print(f"   Załadowano {len(roster)} zawodników.\n")

    meter_value = args.meter if args.meter is not None else compute_meter_value(args.k)
    rng = np.random.default_rng()

    if args.ko_bracket:
        print(f"→ Tryb KO single-elim (bracket={args.ko_bracket}). randomness={randomness}, elite_regress={elite_regress}")
        kwal_df, kval_rank, contest_rows, klasyf, extra_sheets = simulate_ko_single_elim(
            roster=roster, K=args.k, HS=args.hs, meter_value=meter_value,
            bracket_size=int(args.ko_bracket),
            wind_ms_mean=args.wind_mean, wind_ms_sd=args.wind_sd,
            gate_base=args.gate, gate_points_per_step=4.0,
            p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
            rng=rng, randomness=randomness, elite_regress=elite_regress,
            wind_phi=wind_phi, wind_takeoff_gain=args.wind_takeoff_gain,
            wind_flight_gain=args.wind_flight_gain, judges_rho=judges_rho
        )
        extra = extra_sheets
    elif args.ko:
        print(f"→ Tryb KO (T4S). randomness={randomness}, elite_regress={elite_regress}")
        kwal_df, kval_rank, contest_rows, klasyf, extra_sheets = simulate_ko_competition(
            roster=roster, K=args.k, HS=args.hs, meter_value=meter_value,
            qual_spots=int(args.qual_spots),
            wind_ms_mean=args.wind_mean, wind_ms_sd=args.wind_sd,
            gate_base=args.gate, gate_points_per_step=4.0,
            p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
            rng=rng, randomness=randomness, elite_regress=elite_regress,
            wind_phi=wind_phi, wind_takeoff_gain=args.wind_takeoff_gain,
            wind_flight_gain=args.wind_flight_gain, judges_rho=judges_rho
        )
        extra = extra_sheets
    else:
        round_cuts = [int(x) for x in str(args.round_cuts).split(",") if str(x).strip()]
        print(f"→ Tryb klasyczny. random={randomness}, elite_regress={elite_regress}, rundy={round_cuts}")
        kwal_df, kval_rank, contest_rows, klasyf = simulate_competition(
            roster=roster, round_cuts=round_cuts, K=args.k, HS=args.hs, meter_value=meter_value,
            wind_ms_mean=args.wind_mean, wind_ms_sd=args.wind_sd,
            gate_base=args.gate, gate_points_per_step=4.0,
            p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
            rng=rng, randomness=randomness, elite_regress=elite_regress,
            wind_phi=wind_phi, wind_takeoff_gain=args.wind_takeoff_gain,
            wind_flight_gain=args.wind_flight_gain, judges_rho=judges_rho,
            qual_spots=int(args.qual_spots)
        )
        extra = None

    print("→ Zapisuję wyniki do Excela…")
    outpath = save_to_excel(roster, kwal_df, kval_rank, contest_rows, klasyf, outdir, args.hill_name, extra_sheets=extra)
    print(f"✔ Zapisano: {outpath}\n")

    print("Klasyfikacja kwalifikacji – Top 10:")
    print(kval_rank[["Miejsce", "Zawodnik", "Kraj", "Odl.Q", "Punkty"]].head(10).to_string(index=False))

    # dynamic print final classification
    dist_cols = [c for c in klasyf.columns if c.startswith("Odl.")]
    cols = ["Miejsce", "Zawodnik", "Kraj"] + dist_cols + ["Punkty"]
    print("\nKlasyfikacja konkursu – Top 10:")
    print(klasyf[cols].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
