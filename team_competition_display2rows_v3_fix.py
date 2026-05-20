# -*- coding: utf-8 -*-
"""
Team competition helpers (2-row table, proper fall parsing) – FIXED v2
- Jumper1..Jumper4 mapped strictly by OrderKey 1..4.
- Robust recompute of style and distance points RIGHT BEFORE export.
- Clean Excel writer with explicit column order.
"""

from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import re

from ski_jump_simulator_random_v6 import compute_meter_value, simulate_round


def load_roster(excel_path: Path, sheet: str = "Arkusz2") -> pd.DataFrame:
    records = []
    current_country = None
    raw = pd.read_excel(excel_path, sheet_name=sheet, header=None)
    for _, row in raw.iterrows():
        name_or_country = str(row[0]).strip() if not pd.isna(row[0]) else None
        um = row[2]
        forma = row[3]
        if name_or_country and (pd.isna(um) and pd.isna(forma)):
            current_country = name_or_country
        elif name_or_country and current_country and not pd.isna(um) and not pd.isna(forma):
            if len(name_or_country) >= 3:
                records.append({"Kraj": current_country, "Zawodnik": name_or_country, "UM": um, "Forma": forma})
    return pd.DataFrame(records)


def as_float(series, default=0.0):
    return pd.to_numeric(series, errors="coerce").fillna(default).astype("float64")


def parse_distance_and_fall(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy()
    out = df.copy()

    if "Upadek" in out.columns:
        base_fall = as_float(out["Upadek"], default=0.0) > 0
    else:
        base_fall = pd.Series(False, index=out.index)

    dist_text = None
    if "Odległość" in out.columns:
        dist_text = out["Odległość"].astype(str)
    elif "Odległość (m)" in out.columns and not pd.api.types.is_numeric_dtype(out["Odległość (m)"]):
        dist_text = out["Odległość (m)"].astype(str)

    star_fall = pd.Series(False, index=out.index)
    if dist_text is not None:
        star_fall = dist_text.fillna("").str.contains(r"\*")

    out["Upadek"] = (base_fall | star_fall).astype("float64")

    if "Odległość (m)" in out.columns and not pd.api.types.is_numeric_dtype(out["Odległość (m)"]):
        dist_num = (
            out["Odległość (m)"].astype(str)
            .str.replace(",", ".", regex=False)
            .str.replace(r"[^0-9\.\-]", "", regex=True)
        )
        out["Odległość (m)"] = pd.to_numeric(dist_num, errors="coerce")
    elif "Odległość (m)" not in out.columns and "Odległość" in out.columns:
        dist_num = (
            out["Odległość"].astype(str)
            .str.replace(",", ".", regex=False)
            .str.replace(r"[^0-9\.\-]", "", regex=True)
        )
        out["Odległość (m)"] = pd.to_numeric(dist_num, errors="coerce")

    return out


def recompute_round_metrics(df: pd.DataFrame, K: int, meter_value: float) -> pd.DataFrame:
    """
    Recompute Odrzucona min/max, Noty stylowe, Punkty za odległość, Punkty rundy
    from judge columns and Odległość (m) to avoid any stale merges.
    """
    if df is None or df.empty:
        return df.copy()
    df = parse_distance_and_fall(df)

    # style from 5 judges
    judge_cols = ["Sędzia1","Sędzia2","Sędzia3","Sędzia4","Sędzia5"]
    if all(c in df.columns for c in judge_cols):
        judges = df[judge_cols].apply(as_float)
        rej_min = judges.min(axis=1)
        rej_max = judges.max(axis=1)
        style = judges.sum(axis=1) - rej_min - rej_max
        df["Odrzucona min"] = rej_min.round(1)
        df["Odrzucona max"] = rej_max.round(1)
        df["Noty stylowe"] = style.round(1)
    else:
        for c in ["Odrzucona min","Odrzucona max","Noty stylowe"]:
            if c not in df.columns: df[c] = np.nan

    # distance points: FIS = 60 + (d-K)*mv (normal hill 60 at K)
    if "Odległość (m)" in df.columns:
        dist = as_float(df["Odległość (m)"], default=np.nan)
        dist_pts = 60.0 + (dist - float(K)) * float(meter_value)
        df["Punkty za odległość"] = dist_pts.round(1)
    else:
        df["Punkty za odległość"] = np.nan

    # comps
    wind = as_float(df["Kompensacja wiatru"], default=0.0) if "Kompensacja wiatru" in df.columns else 0.0
    gate = as_float(df["Kompensacja belki"], default=0.0)  if "Kompensacja belki"  in df.columns else 0.0

    total = df["Punkty za odległość"].astype(float) + df["Noty stylowe"].astype(float) + wind + gate
    df["Punkty rundy"] = total.round(1)

    return df


def normalize_round_df(df: pd.DataFrame, K: int, meter_value: float) -> pd.DataFrame:
    # Keep backward compatibility but use recompute to guarantee correctness
    return recompute_round_metrics(df, K, meter_value)


def simulate_team_competition(
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
    randomness: float = 0.35,
    elite_regress: float = 1.0,
    wind_phi: float = 0.75,
    wind_takeoff_gain: float = 0.5,
    wind_flight_gain: float = 2.2,
    judges_rho: float = 0.55,
):
    if meter_value is None:
        meter_value = compute_meter_value(K)
    rng_loc = rng or np.random.default_rng()

    teams = []
    for kraj, group in roster.groupby("Kraj"):
        if kraj == "N/A" or pd.isna(kraj):
            continue
        if len(group) >= 4:
            if "OrderKey" in group.columns and group["OrderKey"].notna().any():
                top4 = group.sort_values(["OrderKey","UM"], ascending=[True, False]).head(4)
            else:
                top4 = group.sort_values("UM", ascending=False).head(4)
            teams.append((kraj, top4))

    if not teams:
        return None, None, None, None

    # Round 1
    team_scores_1, detailed_1 = [], []
    for kraj, members in teams:
        r1 = simulate_round(
            members, K, HS, meter_value,
            wind_ms_mean, wind_ms_sd,
            gate_base, gate_points_per_step,
            p_gate_change, max_gate_delta, rng_loc,
            randomness, elite_regress,
            wind_phi, wind_takeoff_gain,
            wind_flight_gain, judges_rho
        )
        r1 = recompute_round_metrics(r1, K, meter_value)
        if "OrderKey" in members.columns and "Zawodnik" in r1.columns:
            ok_map = members.set_index("Zawodnik")["OrderKey"]
            r1["OrderKey"] = r1["Zawodnik"].map(ok_map)
        team_points = float(r1["Punkty rundy"].sum())
        team_scores_1.append((kraj, team_points))
        detailed_1.append(r1.assign(Druzyna=kraj, Kraj=members.iloc[0]["Kraj"], Seria=1))

    df_r1 = pd.concat(detailed_1, ignore_index=True)
    team_scores_1 = pd.DataFrame(team_scores_1, columns=["Druzyna", "Punkty1"]).sort_values("Punkty1", ascending=False)
    finalists = set(team_scores_1.head(8)["Druzyna"])

    # Round 2
    team_scores_2, detailed_2 = [], []
    for kraj, members in teams:
        if kraj not in finalists:
            continue
        r2 = simulate_round(
            members, K, HS, meter_value,
            wind_ms_mean, wind_ms_sd,
            gate_base, gate_points_per_step,
            p_gate_change, max_gate_delta, rng_loc,
            randomness, elite_regress,
            wind_phi, wind_takeoff_gain,
            wind_flight_gain, judges_rho
        )
        r2 = recompute_round_metrics(r2, K, meter_value)
        if "OrderKey" in members.columns and "Zawodnik" in r2.columns:
            ok_map = members.set_index("Zawodnik")["OrderKey"]
            r2["OrderKey"] = r2["Zawodnik"].map(ok_map)
        team_points = float(r2["Punkty rundy"].sum())
        team_scores_2.append((kraj, team_points))
        detailed_2.append(r2.assign(Druzyna=kraj, Kraj=members.iloc[0]["Kraj"], Seria=2))

    df_r2 = pd.concat(detailed_2, ignore_index=True) if detailed_2 else pd.DataFrame()
    team_scores_2 = pd.DataFrame(team_scores_2, columns=["Druzyna", "Punkty2"])

    klasyf = team_scores_1.merge(team_scores_2, on="Druzyna", how="left").fillna(0)
    klasyf["Punkty"] = klasyf["Punkty1"] + klasyf["Punkty2"]
    klasyf = klasyf.sort_values("Punkty", ascending=False).reset_index(drop=True)
    klasyf.insert(0, "Miejsce", (-klasyf["Punkty"]).rank(method="min").astype(int))

    all_rounds = pd.concat([df_r1, df_r2], ignore_index=True) if not df_r2.empty else df_r1
    return df_r1, df_r2, klasyf, all_rounds


def _fmt_dist_from_row(row: pd.Series) -> str:
    need_star = False
    try:
        u = row.get("Upadek", 0)
        if isinstance(u, (int, float)) and float(u) > 0:
            need_star = True
        elif str(u).strip().lower() in ("true","1","1.0","tak","yes"):
            need_star = True
    except Exception:
        pass

    txt = str(row.get("Odległość", "") or "").strip()
    if txt:
        base = txt.replace(",", ".").replace("*", "").strip()
        if base and not base.endswith("m"):
            base += "m"
        return f"{base}{'*' if need_star or ('*' in txt) else ''}"

    val = row.get("Odległość (m)", None)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    s = f"{float(val):.2f}m"
    return f"{s}*" if need_star else s


def _dist_list_by_orderkey(team_df: pd.DataFrame) -> list[str]:
    if team_df is None or getattr(team_df, "empty", True):
        return ["", "", "", ""]
    df = team_df.copy()
    df = parse_distance_and_fall(df)
    df["OrderKey"] = pd.to_numeric(df.get("OrderKey"), errors="coerce")
    slots = {1:"", 2:"", 3:"", 4:""}
    if df["OrderKey"].notna().any():
        for _, r in df.iterrows():
            ok = r.get("OrderKey")
            if pd.notna(ok):
                ok_i = int(ok)
                if ok_i in slots:
                    slots[ok_i] = _fmt_dist_from_row(r)
        return [slots[1], slots[2], slots[3], slots[4]]
    df = df.sort_values(["Zawodnik"], ascending=[True], kind="mergesort")
    out = []
    for _, r in df.head(4).iterrows():
        out.append(_fmt_dist_from_row(r))
    while len(out) < 4:
        out.append("")
    return out

def build_two_row_table(roster, df_r1, df_r2, klasyf) -> pd.DataFrame:
    import pandas as pd
    import numpy as np

    # --- helpers ---
    def _col(df, *cands):
        if not isinstance(df, pd.DataFrame):
            return None
        for c in cands:
            if c in df.columns:
                return c
        return None

    def _series_or_zeros(df, colname):
        # Zwraca Series dopasowaną do df.index; gdy brak kolumny → zera
        if not isinstance(df, pd.DataFrame) or len(df) == 0:
            return pd.Series([], dtype="float64")
        if (colname is None) or (colname not in df.columns):
            return pd.Series(0.0, index=df.index, dtype="float64")
        return pd.to_numeric(df[colname], errors="coerce").fillna(0.0)

    def _dist_list_by_orderkey(team_df: pd.DataFrame) -> list[str]:
        if team_df is None or len(team_df) == 0:
            return ["", "", "", ""]
        df = team_df.copy()
        name_c = _col(df, "Zawodnik")
        dist_txt = _col(df, "Odległość")
        dist_num = _col(df, "Odległość (m)")
        ok = _col(df, "OrderKey")
        if ok is not None:
            try:
                df["_OK_"] = pd.to_numeric(df[ok], errors="coerce").fillna(9999)
            except Exception:
                df["_OK_"] = 9999
            by = ["_OK_"] + ([name_c] if name_c else [])
            df = df.sort_values(by, ascending=[True] * len(by), kind="mergesort")
        # Preferuj gotowy tekst; w przeciwnym razie sformatuj z wartości liczbowej
        if dist_txt and df[dist_txt].astype(str).str.strip().ne("").any():
            s = df[dist_txt].astype(str)
        else:
            v = pd.to_numeric(df[dist_num], errors="coerce") if dist_num else pd.Series([np.nan] * len(df))
            s = v.map(lambda x: "" if pd.isna(x) else f"{float(x):.2f}m")
        out = list(s.head(4))
        out += [""] * (4 - len(out))
        return out[:4]

    # --- mapowanie team -> kod kraju ---
    nat_per_team = {}
    if isinstance(df_r1, pd.DataFrame) and _col(df_r1, "Druzyna", "Drużyna") and _col(df_r1, "Kraj"):
        tcol = _col(df_r1, "Druzyna", "Drużyna")
        nat_per_team.update(
            df_r1.dropna(subset=[tcol, "Kraj"]).drop_duplicates(tcol).set_index(tcol)["Kraj"].to_dict()
        )
    if isinstance(df_r2, pd.DataFrame) and _col(df_r2, "Druzyna", "Drużyna") and _col(df_r2, "Kraj"):
        tcol = _col(df_r2, "Druzyna", "Drużyna")
        nat_per_team.update(
            df_r2.dropna(subset=[tcol, "Kraj"]).drop_duplicates(tcol).set_index(tcol)["Kraj"].to_dict()
        )

    # --- sumy punktów per team w seriach ---
    r1_map, r2_map = {}, {}
    if isinstance(df_r1, pd.DataFrame) and len(df_r1) > 0:
        key1 = _col(df_r1, "Druzyna", "Drużyna") or _col(df_r1, "Kraj")
        pts1 = _col(df_r1, "Punkty rundy", "Punkty")
        if key1 and pts1:
            r1_map = _series_or_zeros(df_r1, pts1).groupby(df_r1[key1]).sum().to_dict()
    if isinstance(df_r2, pd.DataFrame) and len(df_r2) > 0:
        key2 = _col(df_r2, "Druzyna", "Drużyna") or _col(df_r2, "Kraj")
        pts2 = _col(df_r2, "Punkty rundy", "Punkty")
        if key2 and pts2:
            r2_map = _series_or_zeros(df_r2, pts2).groupby(df_r2[key2]).sum().to_dict()

    tcol1 = _col(df_r1, "Druzyna", "Drużyna")
    tcol2 = _col(df_r2, "Druzyna", "Drużyna")

    rows = []
    for _, row in klasyf.iterrows():
        miejsce = int(row["Miejsce"]) if pd.notna(row.get("Miejsce")) else ""
        team = row.get("Drużyna", row.get("Druzyna", ""))
        team = "" if pd.isna(team) else str(team)
        kraj = nat_per_team.get(team, "")

        r1_team = df_r1[df_r1[tcol1] == team] if isinstance(df_r1, pd.DataFrame) and tcol1 else pd.DataFrame()
        r2_team = df_r2[df_r2[tcol2] == team] if isinstance(df_r2, pd.DataFrame) and tcol2 else pd.DataFrame()

        s1 = _dist_list_by_orderkey(r1_team)
        s2 = _dist_list_by_orderkey(r2_team)

        pts1 = _col(r1_team, "Punkty rundy", "Punkty")
        pts2 = _col(r2_team, "Punkty rundy", "Punkty")
        suma1 = float(_series_or_zeros(r1_team, pts1).sum()) if len(r1_team) else 0.0
        suma2 = float(_series_or_zeros(r2_team, pts2).sum()) if len(r2_team) else 0.0

        rows.append({
            "Miejsce": miejsce,
            "Drużyna": team,
            "Kraj": kraj,
            "Jumper1": s1[0], "Jumper2": s1[1], "Jumper3": s1[2], "Jumper4": s1[3],
            "Suma (R1)": round(suma1, 1),
            "Suma (R2)": ""
        })
        rows.append({
            "Miejsce": "",
            "Drużyna": "",
            "Kraj": "",
            "Jumper1": s2[0], "Jumper2": s2[1], "Jumper3": s2[2], "Jumper4": s2[3],
            "Suma (R1)": "",
            "Suma (R2)": round(suma2, 1) if suma2 else ""
        })

    out = pd.DataFrame(rows, columns=[
        "Miejsce","Drużyna","Kraj","Jumper1","Jumper2","Jumper3","Jumper4","Suma (R1)","Suma (R2)"
    ])

    out = pd.DataFrame(rows, columns=[
        "Miejsce","Drużyna","Kraj","Jumper1","Jumper2","Jumper3","Jumper4","Suma (R1)","Suma (R2)"
    ])

    # usuń kolumny Suma (R1) i Suma (R2) – chcemy tylko jedną wspólną „Suma”
    out = out.drop(columns=[c for c in out.columns if "Suma (R" in c], errors="ignore")


    # --- kolumna SUMA tylko w pierwszym wierszu pary ---
    def _sum_total_for_row(r):
        team = str(r.get("Drużyna", "") or "")
        code = str(r.get("Kraj", "") or "")
        v1 = r1_map.get(team, r1_map.get(code, 0.0))
        v2 = r2_map.get(team, r2_map.get(code, 0.0))
        try:
            return round(float(v1) + float(v2), 1)
        except Exception:
            return 0.0

    suma_col = []
    for i in range(len(out)):
        suma_col.append(f"{_sum_total_for_row(out.iloc[i]):.1f}" if i % 2 == 0 else "")
    out["Suma"] = suma_col

    # porządek kolumn
    desired = ["Miejsce","Drużyna","Kraj","Jumper1","Jumper2","Jumper3","Jumper4","Suma"]
    out = out[[c for c in desired if c in out.columns] + [c for c in out.columns if c not in desired]]

    return out

def build_falls_sheet(all_rounds: pd.DataFrame) -> pd.DataFrame:
    """
    Zwraca ramkę upadków. Preferuje tekstową 'Odległość' (z gwiazdką) i
    porządek kolumn do podglądu/Excel:
      Zawodnik, Kraj, Seria, Odległość, Punkty rundy
    Zostawia też techniczne 'Druzyna'/'OrderKey' jeśli były – na końcu.
    """
    base_cols = ["Druzyna","Kraj","Zawodnik","Seria","Runda","Odległość","Odległość (m)","Upadek","Punkty rundy","OrderKey"]
    if all_rounds is None or getattr(all_rounds, "empty", True):
        return pd.DataFrame(columns=["Zawodnik","Kraj","Seria","Odległość","Punkty rundy"])

    df = parse_distance_and_fall(all_rounds)

    # wymuś binarną kolumnę Upadek
    try:
        df["Upadek"] = pd.to_numeric(df.get("Upadek", 0.0), errors="coerce").fillna(0.0)
    except Exception:
        df["Upadek"] = 0.0

    # filtr: tylko upadki
    falls = df[df["Upadek"] > 0].copy()
    if falls.empty:
        return pd.DataFrame(columns=["Zawodnik","Kraj","Seria","Odległość","Punkty rundy"])

    # preferencje kolumn
    if "Seria" not in falls.columns and "Runda" in falls.columns:
        falls.rename(columns={"Runda": "Seria"}, inplace=True)
    if "Odległość" not in falls.columns and "Odległość (m)" in falls.columns:
        falls.rename(columns={"Odległość (m)": "Odległość"}, inplace=True)

    # sort stabilny
    sort_cols = [c for c in ["Druzyna","Seria","OrderKey","Zawodnik"] if c in falls.columns]
    if sort_cols:
        falls = falls.sort_values(sort_cols, kind="mergesort")

    desired = ["Zawodnik","Kraj","Seria","Odległość","Punkty rundy"]
    tail = [c for c in ["Druzyna","OrderKey"] if c in falls.columns]
    cols_out = [c for c in desired if c in falls.columns] + tail
    return falls[cols_out].reset_index(drop=True)

# ---------- NEW: clean Excel export that recomputes before saving ----------
def _prepare_round_for_excel(df_round: pd.DataFrame, K: int, meter_value: float) -> pd.DataFrame:
    df = recompute_round_metrics(df_round, K, meter_value)
    desired = [
        "Zawodnik","Kraj","Druzyna","Seria",
        "Odległość (m)","Bramka",
        "Sędzia1","Sędzia2","Sędzia3","Sędzia4","Sędzia5",
        "Odrzucona min","Odrzucona max","Noty stylowe",
        "Kompensacja wiatru","Kompensacja belki",
        "Punkty za odległość","Punkty rundy","OrderKey"
    ]
    have = [c for c in desired if c in df.columns]
    df = df[have].copy()
    return df


def save_xlsx_team(path: Path, K: int, meter_value: float, *, df_r1=None, df_r2=None, klasyf=None, tabela=None, upadki=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as w:
        if isinstance(df_r1, pd.DataFrame) and not df_r1.empty:
            _prepare_round_for_excel(df_r1, K, meter_value).to_excel(w, sheet_name="Seria1", index=False)
        if isinstance(df_r2, pd.DataFrame) and not df_r2.empty:
            _prepare_round_for_excel(df_r2, K, meter_value).to_excel(w, sheet_name="Seria2", index=False)
        if isinstance(klasyf, pd.DataFrame) and not klasyf.empty:
            klasyf.to_excel(w, sheet_name="Klasyfikacja", index=False)
        if isinstance(tabela, pd.DataFrame) and not tabela.empty:
            tabela.to_excel(w, sheet_name="Tabela 2w", index=False)
        if isinstance(upadki, pd.DataFrame) and not upadki.empty:
            upadki.to_excel(w, sheet_name="Upadki", index=False)
    return path


def main():
    p = argparse.ArgumentParser(description="Team competition – strict OrderKey mapping + clean Excel export")
    p.add_argument("--excel", required=True, help="Path to Excel roster")
    p.add_argument("--sheet", default="Arkusz2")
    p.add_argument("--hill-name", default="Zakopane")
    p.add_argument("--k", type=int, default=125)
    p.add_argument("--hs", type=int, default=140)
    p.add_argument("--meter", type=float, default=None)
    p.add_argument("--outdir", default="wyniki")
    args = p.parse_args()

    excel_path = Path(args.excel)
    roster = load_roster(excel_path, sheet=args.sheet)

    meter_value = args.meter if args.meter is not None else compute_meter_value(args.k)

    df_r1, df_r2, klasyf, all_rounds = simulate_team_competition(
        roster, K=args.k, HS=args.hs, meter_value=meter_value
    )
    if klasyf is None or isinstance(klasyf, type(None)):
        print("Brak drużyn.")
        return

    two_rows = build_two_row_table(roster, df_r1, df_r2, klasyf)
    falls_df = build_falls_sheet(all_rounds)

    out = Path(args.outdir) / f"TEAM_{args.hill_name}.xlsx"
    save_xlsx_team(out, args.k, meter_value, df_r1=df_r1, df_r2=df_r2, klasyf=klasyf, tabela=two_rows, upadki=falls_df)
    print(str(out.resolve()))


if __name__ == "__main__":
    main()
