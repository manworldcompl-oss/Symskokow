
import pandas as pd
import numpy as np
from pathlib import Path
import re

import ski_jump_simulator_random_v6 as sim
from team_competition_display2rows_v3_fix import parse_distance_and_fall

# === BYE & bracket helpers ===
def _bracket_seed_order(n: int = 64) -> list[int]:
    # 1,64,32,33,16,49,17,48, ...
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


def _pair_indices(n: int):
    """Adjacent pairing indices: (0,1), (2,3), ..."""
    return [(i, i+1) for i in range(0, n, 2)]


def _balanced_bracket_order(n: int):
    """Return index order (0-based) for balanced 64-seed bracket like:
    1-64, 32-33, 16-49, 17-48, ... (pairs become adjacent).
    We generate recursively: for size m=2*k from order of k,
    interleave x and m+1-x.
    """
    order = [1]
    while len(order) < n:
        m = len(order) * 2
        order = [y for x in order for y in (x, m + 1 - x)]
    return [x-1 for x in order]
def _prep_field(df_rank: pd.DataFrame, top_n: int = 64) -> pd.DataFrame:
    """Take top N from kwalifikacje rank (descending by 'Punkty'), attach Seed."""
    # df_rank expected sorted by 'Punkty' desc with 'Miejsce' or we enforce
    r = df_rank.copy()
    if "Punkty" in r.columns:
        r = r.sort_values("Punkty", ascending=False, kind="stable").reset_index(drop=True)
    r["Seed"] = np.arange(1, len(r)+1)
    field = r.head(top_n).reset_index(drop=True)
    return field

def _roster_from_field(field: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ["Zawodnik","UM","Forma","Kraj"] if c in field.columns]
    return field[cols].copy()

def _round_label(r: int) -> str:
    labels = {1:"R1 (64)", 2:"R2 (32)", 3:"R3 (16)", 4:"QF (8)", 5:"SF (4)", 6:"F (2)"}
    return labels.get(r, f"R{r}")

# --- BYE helpers (ko64_bracket.py) ---
def _bracket_seed_order(n: int = 64) -> list[int]:
    # 1,64,32,33,16,49,17,48, ... (klasyczny „balanced bracket”)
    order = [1]
    while len(order) < n:
        m = len(order) * 2
        order = [y for x in order for y in (x, m + 1 - x)]
    return order  # 1-based

def _fill_byes_to_64(field: pd.DataFrame, size: int = 64) -> pd.DataFrame:
    f = field.copy()
    f["Seed"] = np.arange(1, len(f) + 1)  # seed wg kwalifikacji
    if len(f) >= size:
        return f.head(size).reset_index(drop=True)
    byes = []
    for seed in range(len(f) + 1, size + 1):
        byes.append({"Seed": seed, "Zawodnik": f"BYE {seed}", "UM": 0.0, "Forma": 0.0, "Kraj": "", "IsBYE": True})
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
    ability_scale: float = 100.0,
):
    """Return (kwal_df, kval_rank, contest_rows, klasyf, extra_sheets) with full KO64 bracket."""
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
        ability_scale=ability_scale,
        sort_output=True,
    )
    # ranking kwalifikacji
    kval_rank = kwal_df.copy()
    if "Punkty rundy" in kval_rank.columns:
        kval_rank.rename(columns={"Punkty rundy":"Punkty"}, inplace=True)
    if "Miejsce w rundzie" in kval_rank.columns:
        kval_rank.rename(columns={"Miejsce w rundzie":"Miejsce"}, inplace=True)

    field = _fill_byes_to_64(field, 64)        # NOWE
    seed_order = _bracket_seed_order(64)       # 1..64
    current = field.set_index("Seed").loc[seed_order].reset_index()

    # --- KO64 tournament ---
    def _normalize_falls(df):
        d = df.copy()

        # bazowa flaga (może być bool/0-1/"PRAWDA"/"FAŁSZ")
        if "Upadek" in d.columns:
            base = pd.to_numeric(d["Upadek"].replace({"PRAWDA":1,"FAŁSZ":0}), errors="coerce").fillna(0) > 0
        else:
            base = pd.Series(False, index=d.index)

        # gwiazdka w KO64 przy kolumnie "Odległość" (tekst z '*')
        star_text = pd.Series(False, index=d.index)
        for col in ["Odległość", "Odległość (t)"]:
            if col in d.columns:
                star_text = star_text | d[col].astype(str).str.contains(r"\*")

        # awaryjnie: gdyby były kolumny Odl1..Odl6
        star_ol = pd.Series(False, index=d.index)
        ol_cols = [c for c in d.columns if re.match(r"^Odl\d+$", str(c))]
        if ol_cols:
            star_ol = d[ol_cols].astype(str).apply(lambda s: s.str.contains(r"\*")).any(axis=1)

        d["Upadek"] = (base | star_text | star_ol).astype(int)  # 0/1 – trwale podmieniamy
        return d

    bracket_rows = []
    contest_all = [ _normalize_falls(df) for df in contest_all ]

    # dopełnij BYE i ustaw stały układ R1 (seed 1..64)
    field = _fill_byes_to_64(field, 64)
    seed_order = _bracket_seed_order(64)
    current = field.set_index("Seed").loc[seed_order][["Seed","Zawodnik","UM","Forma","Kraj","IsBYE"]].reset_index(drop=True)

    round_num = 1
    while len(current) >= 2:
        n = len(current)
        pairs = _pair_indices(n)

        rows_this_round = []
        winners_rows = []

        for pid, (i, j) in enumerate(pairs, start=1):
            A = current.iloc[i]; B = current.iloc[j]
            a_is_bye = bool(A.get("IsBYE", False))
            b_is_bye = bool(B.get("IsBYE", False))

            if a_is_bye or b_is_bye:
                def mkrow(rec):
                    return {
                        "Zawodnik": rec["Zawodnik"], "UM": rec.get("UM", np.nan),
                        "Forma": rec.get("Forma", np.nan), "Kraj": rec.get("Kraj",""),
                        "Odległość (m)": np.nan, "Noty stylowe": 0.0,
                        "Punkty za odległość": 0.0, "Kompensacja wiatru": 0.0,
                        "Kompensacja belki": 0.0, "Punkty rundy": 0.0
                    }
                row_a = mkrow(A); row_b = mkrow(B)
            else:
                r_pair = sim.simulate_round(
                    roster=current.loc[[i, j], ["Zawodnik","UM","Forma","Kraj"]],
                    K=K, HS=HS, meter_value=meter_value,
                    wind_ms_mean=wind_ms_mean, wind_ms_sd=wind_ms_sd,
                    gate_base=gate_base, gate_points_per_step=gate_points_per_step,
                    p_gate_change=p_gate_change, max_gate_delta=max_gate_delta,
                    rng=rng, randomness=randomness, elite_regress=elite_regress,
                    wind_phi=wind_phi, wind_takeoff_gain=wind_takeoff_gain,
                    wind_flight_gain=wind_flight_gain, judges_rho=judges_rho,
                    ability_scale=ability_scale,
                    sort_output=False
                )
                row_a = r_pair.iloc[0].to_dict(); row_b = r_pair.iloc[1].to_dict()

            row_a.update({"Seed": int(A["Seed"]), "Para": pid, "Runda": round_num})
            row_b.update({"Seed": int(B["Seed"]), "Para": pid, "Runda": round_num})
            rows_this_round.extend([row_a, row_b])

            pa = float(row_a.get("Punkty rundy", 0.0)); pb = float(row_b.get("Punkty rundy", 0.0))
            winner = A if (pa > pb or (pa == pb and int(A["Seed"]) < int(B["Seed"]))) else B

            winners_rows.append({
                "Seed": int(winner["Seed"]), "Zawodnik": winner["Zawodnik"],
                "UM": winner.get("UM", np.nan), "Forma": winner.get("Forma", np.nan),
                "Kraj": winner.get("Kraj",""), "IsBYE": bool(winner.get("IsBYE", False))
            })

            bracket_rows.append({
                "Runda": _round_label(round_num), "Para": pid,
                "Seed A": int(A["Seed"]), "Zawodnik A": A["Zawodnik"], "Kraj A": A.get("Kraj",""),
                "Odl A (m)": row_a.get("Odległość (m)", np.nan), "Punkty A": pa,
                "Seed B": int(B["Seed"]), "Zawodnik B": B["Zawodnik"], "Kraj B": B.get("Kraj",""),
                "Odl B (m)": row_b.get("Odległość (m)", np.nan), "Punkty B": pb,
                "Zwycięzca (Seed)": int(winner["Seed"]), "Zwycięzca": winner["Zawodnik"]
            })

        contest_all.append(pd.DataFrame(rows_this_round))
        current = pd.DataFrame(winners_rows).reset_index(drop=True)
        round_num += 1

    # --- Final classification ---
    # Build placement by elimination round:
    # Rounds: 1:64->32 losers get places 33-64, 2:32->16 -> 17-32, 3:16->8 -> 9-16, 4:8->4 -> 5-8, 5:4->2 -> 3-4, 6:2->1 -> 1-2
    # We reconstruct losers per round from contest_all.
    elim_groups = {}
    for r_df in contest_all:
        r = int(r_df["Runda"].iloc[0])
        losers = []
        for pair_id in range(1, r_df["Para"].max()+1):
            a = r_df[r_df["Para"]==pair_id].iloc[0]
            b = r_df[r_df["Para"]==pair_id].iloc[1]
            pts_a = float(a["Punkty rundy"]); pts_b = float(b["Punkty rundy"])
            if pts_a > pts_b or (pts_a == pts_b and int(a["Seed"]) < int(b["Seed"])):
                loser = b
            else:
                loser = a
            losers.append(loser)
        elim_groups[r] = pd.DataFrame(losers)

    # determine champion and runner-up from last round (r=6)
    final_df = contest_all[-1]
    a = final_df.iloc[0]; b = final_df.iloc[1]
    pts_a = float(a["Punkty rundy"]); pts_b = float(b["Punkty rundy"])
    if pts_a > pts_b or (pts_a == pts_b and int(a["Seed"]) < int(b["Seed"])):
        champ, vice = a, b
    else:
        champ, vice = b, a

    # helper to sort losers by points (desc), then by better seed (asc)
    def _sort_group(df):
        df = df.copy()
        df["__pts"] = pd.to_numeric(df["Punkty rundy"], errors="coerce").fillna(0.0)
        df["__seed"] = pd.to_numeric(df["Seed"], errors="coerce").fillna(9999)
        return df.sort_values(["__pts", "__seed"], ascending=[False, True]).drop(columns=["__pts","__seed"])

    klasyf_rows = []
    # 1st, 2nd
    klasyf_rows.append({"Miejsce": 1, "Zawodnik": champ["Zawodnik"], "Kraj": champ.get("Kraj",""), "Seed": int(champ["Seed"]), "Punkty": float(champ["Punkty rundy"])})
    klasyf_rows.append({"Miejsce": 2, "Zawodnik": vice["Zawodnik"], "Kraj": vice.get("Kraj",""), "Seed": int(vice["Seed"]), "Punkty": float(vice["Punkty rundy"])})

    # SF losers -> 3-4
    if 5 in elim_groups:
        g = _sort_group(elim_groups[5]).reset_index(drop=True)
        for i, row in g.iterrows():
            klasyf_rows.append({"Miejsce": 3+i, "Zawodnik": row["Zawodnik"], "Kraj": row.get("Kraj",""), "Seed": int(row["Seed"]), "Punkty": float(row["Punkty rundy"])})

    # QF losers -> 5-8
    if 4 in elim_groups:
        g = _sort_group(elim_groups[4]).reset_index(drop=True)
        for i, row in g.iterrows():
            klasyf_rows.append({"Miejsce": 5+i, "Zawodnik": row["Zawodnik"], "Kraj": row.get("Kraj",""), "Seed": int(row["Seed"]), "Punkty": float(row["Punkty rundy"])})

    # R3 losers -> 9-16
    if 3 in elim_groups:
        g = _sort_group(elim_groups[3]).reset_index(drop=True)
        for i, row in g.iterrows():
            klasyf_rows.append({"Miejsce": 9+i, "Zawodnik": row["Zawodnik"], "Kraj": row.get("Kraj",""), "Seed": int(row["Seed"]), "Punkty": float(row["Punkty rundy"])})

    # R2 losers -> 17-32
    if 2 in elim_groups:
        g = _sort_group(elim_groups[2]).reset_index(drop=True)
        for i, row in g.iterrows():
            klasyf_rows.append({"Miejsce": 17+i, "Zawodnik": row["Zawodnik"], "Kraj": row.get("Kraj",""), "Seed": int(row["Seed"]), "Punkty": float(row["Punkty rundy"])})

    # R1 losers -> 33-64
    if 1 in elim_groups:
        g = _sort_group(elim_groups[1]).reset_index(drop=True)
        for i, row in g.iterrows():
            klasyf_rows.append({"Miejsce": 33+i, "Zawodnik": row["Zawodnik"], "Kraj": row.get("Kraj",""), "Seed": int(row["Seed"]), "Punkty": float(row["Punkty rundy"])})

    klasyf = pd.DataFrame(klasyf_rows)
    # Tied places (ex aequo): sort po punktach i miejsca 1,1,3...
    if "Punkty" in klasyf.columns:
        klasyf["Punkty"] = pd.to_numeric(klasyf["Punkty"], errors="coerce").fillna(0.0)
        klasyf = klasyf.sort_values("Punkty", ascending=False, kind="stable").reset_index(drop=True)
        if "Miejsce" in klasyf.columns:
            klasyf.drop(columns=["Miejsce"], inplace=True)
        klasyf.insert(0, "Miejsce", (-klasyf["Punkty"]).rank(method="min").astype(int))

    # "Konkurs - rundy" = concat all rounds
    contest_rows = pd.concat(contest_all, ignore_index=True)
        # --- Konsolidacja / detekcja upadków w KO64 ---
    def _infer_falls_anywhere(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()

        # 1) bazowa flaga (może być bool albo 0/1)
        if "Upadek" in d.columns:
            base = pd.to_numeric(d["Upadek"], errors="coerce").fillna(0.0) > 0
        else:
            base = pd.Series(False, index=d.index)

        # 2) gwiazdka w tekstowej odległości KO64 (np. "239.32*")
        star_from_text = pd.Series(False, index=d.index)
        if "Odległość" in d.columns:
            star_from_text = d["Odległość"].astype(str).fillna("").str.contains(r"\*")

        # 3) awaryjnie: gdyby były kolumny Odl1..Odl6 (np. po przekształceniach)
        star_from_ol = pd.Series(False, index=d.index)
        ol_cols = [c for c in d.columns if re.match(r"^Odl\d+$", str(c))]
        if ol_cols:
            star_from_ol = d[ol_cols].astype(str).apply(lambda s: s.str.contains(r"\*")).any(axis=1)

        # finalna flaga
        d["Upadek"] = (base | star_from_text | star_from_ol).astype("float64")
        return d

    contest_rows = _infer_falls_anywhere(contest_rows)

    # --- Arkusz "Upadki" (zbiorczo ze wszystkich rund) ---
    falls_df = contest_rows.loc[
        pd.to_numeric(contest_rows.get("Upadek", 0.0), errors="coerce").fillna(0.0) > 0,
        # wolimy kolumnę "Odległość" (z gwiazdką), a jeśli jej brak – bierzemy "(m)"
        [c for c in ["Runda", "Zawodnik", "Kraj", "Odległość", "Odległość (m)", "Punkty rundy"] if c in contest_rows.columns]
    ].copy()

    # jeżeli są obie – zostaw tylko "Odległość" (z gwiazdką) do czytelności
    if "Odległość" in falls_df.columns and "Odległość (m)" in falls_df.columns:
        falls_df.drop(columns=["Odległość (m)"], inplace=True)

        # --- Upadki (zbiorczo z wszystkich rund) ---
    try:
        falls_parts = []
        # contest_all to lista DataFrame’ów z każdej rundy (already built above)
        for r_df in contest_all:
            df_r = parse_distance_and_fall(r_df.copy())
            mask = pd.to_numeric(df_r.get("Upadek", 0.0), errors="coerce").fillna(0) > 0
            if mask.any():
                keep_cols = [c for c in ["Runda", "Zawodnik", "Kraj", "Odległość (m)", "Punkty rundy"] if c in df_r.columns]
                falls_parts.append(df_r.loc[mask, keep_cols])
        falls_df = (
            pd.concat(falls_parts, ignore_index=True)
            if falls_parts else
            pd.DataFrame(columns=["Runda", "Zawodnik", "Kraj", "Odległość (m)", "Punkty rundy"])
        )
    except Exception:
        # na wszelki wypadek – nie blokuj całego konkursu, jeśli coś pójdzie nie tak
        falls_df = pd.DataFrame(columns=["Runda", "Zawodnik", "Kraj", "Odległość (m)", "Punkty rundy"])

    # Bracket sheet
    bracket_df = pd.DataFrame(bracket_rows)

    # Transform bracket_df (wide pairs) -> per-athlete rows like KO50 (each jump in its own row)
    if not bracket_df.empty and "Zawodnik A" in bracket_df.columns and "Zawodnik B" in bracket_df.columns:
        rows = []
        for _, r in bracket_df.iterrows():
            for side in ("A","B"):
                rows.append({
                    "Runda": r.get("Runda",""),
                    "Para": r.get("Para",""),
                    "Seed": r.get(f"Seed {side}", ""),
                    "Zawodnik": r.get(f"Zawodnik {side}", ""),
                    "Kraj": r.get(f"Kraj {side}", ""),
                    "Odl.": r.get(f"Odl {side} (m)", np.nan),
                    "Punkty": r.get(f"Punkty {side}", np.nan),
                    "Wygrana": "✓" if str(r.get("Zwycięzca","")) == str(r.get(f"Zawodnik {side}","")) else "✗",
                })
        bracket_df = pd.DataFrame(rows)

        extra_sheets = {
            "KO64 - Drabinka": bracket_df,
            "Upadki": falls_df,   # <<--- NOWE
        }

    return kwal_df, kval_rank, contest_rows, klasyf, extra_sheets
