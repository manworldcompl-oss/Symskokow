
# team_results_export.py
# Minimalny eksport do XLSX bez grzebania w team_competition_gui_embedded.
from __future__ import annotations
import pandas as pd
from pathlib import Path
from excel_saver import save_competition_results
from datetime import datetime

def _safe_name(text: str) -> str:
    return (str(text) or "wynik").strip().replace("/", "-").replace("\\", "-").replace(":", "-")

def _format_filename(pattern: str, hill: str) -> str:
    now = datetime.now()
    mapping = {
        "{hill}": _safe_name(hill),
        "{YYYY}": now.strftime("%Y"),
        "{mm}": now.strftime("%m"),
        "{dd}": now.strftime("%d"),
        "{HH}": now.strftime("%H"),
        "{MM}": now.strftime("%M"),
        "{SS}": now.strftime("%S"),
        "{YYYY-mm-dd_HH-MM}": now.strftime("%Y-%m-%d_%H-%M"),
    }
    out = pattern
    for k, v in mapping.items():
        out = out.replace(k, v)
    return out if out.lower().endswith(".xlsx") else out + ".xlsx"

def export_team_results_xlsx(
    out_dir: str | Path,
    filename_pattern: str,
    hill_name: str,
    kval_df: pd.DataFrame | None = None,
    contest_rows: pd.DataFrame | None = None,
    klasyf_df: pd.DataFrame | None = None,
    extra_sheets: dict[str, pd.DataFrame] | None = None
) -> str:
    import pandas as pd, re
    out_dir = Path(out_dir or "./wyniki")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _format_filename(filename_pattern or "{YYYY-mm-dd_HH-MM}_{hill}", hill_name)

    def _merge_suma_cols(df: pd.DataFrame) -> pd.DataFrame:
        """Jeśli są 'Suma (R1)' i 'Suma (R2)' (dowolne warianty), to zamień na jedną 'Suma'."""
        cols = list(df.columns)
        # znajdź kolumny R1/R2 po regexie, żeby złapać różne spacje, nawiasy, itp.
        r1 = next((c for c in cols if re.search(r"Suma.*R1", str(c), flags=re.I)), None)
        r2 = next((c for c in cols if re.search(r"Suma.*R2", str(c), flags=re.I)), None)
        if not (r1 or r2):
            return df

        dfm = df.copy()
        s1 = pd.to_numeric(dfm[r1], errors="coerce").fillna(0) if r1 in dfm.columns else 0
        s2 = pd.to_numeric(dfm[r2], errors="coerce").fillna(0) if r2 in dfm.columns else 0
        dfm["Suma"] = s1 + s2
        for c in (r1, r2):
            if c in dfm.columns:
                del dfm[c]

        # preferowany układ kolumn jeśli pasuje do Twojej „2-wierszówki”
        desired = ["Miejsce","Drużyna","Kraj","Jumper1","Jumper2","Jumper3","Jumper4","Suma"]
        ordered = [c for c in desired if c in dfm.columns]
        tail = [c for c in dfm.columns if c not in ordered]
        return dfm[ordered + tail] if ordered else dfm

    sheets: dict[str, pd.DataFrame] = {}

    # 1. i 2. seria: zmiana NAZW arkuszy
    if isinstance(kval_df, pd.DataFrame) and not kval_df.empty:
        sheets["1 seria"] = kval_df.copy()

    if isinstance(contest_rows, pd.DataFrame) and not contest_rows.empty:
        sheets["2 seria"] = contest_rows.copy()

    # Klasyfikacja końcowa
    if isinstance(klasyf_df, pd.DataFrame) and not klasyf_df.empty:
        sheets["Klasyfikacja"] = klasyf_df.copy()

    # Dodatkowe arkusze (np. "Klasyfikacja 2-wiersze"): łącz SUMA(R1)+SUMA(R2) w KAŻDYM DF, jeśli występują
    if isinstance(extra_sheets, dict):
        for k, v in extra_sheets.items():
            if isinstance(v, pd.DataFrame):
                name = str(k)[:31]  # limit Excela
                # 'Upadki' zapisujemy nawet gdy puste (nagłówki też są przydatne)
                if name == 'Upadki':
                    sheets[name] = _merge_suma_cols(v)
                elif not v.empty:
                    sheets[name] = _merge_suma_cols(v)
                name = str(k)[:31]  # limit Excela
                sheets[name] = _merge_suma_cols(v)
    # --- NOWE: dodaj arkusz z upadkami ---
    try:
        from team_competition_display2rows_v3_fix import build_falls_sheet
        if "Upadki" not in sheets:
            falls_df = None
            if isinstance(extra_sheets, dict):
                falls_df = extra_sheets.get("Upadki")
            if falls_df is None and isinstance(contest_rows, pd.DataFrame):
                falls_df = build_falls_sheet(contest_rows)
            if isinstance(falls_df, pd.DataFrame):
                sheets["Upadki"] = falls_df  # zapisujemy nawet gdy puste
    except Exception as e:
        print("WARN: nie udało się utworzyć arkusza Upadki:", e)


    if not sheets:
        sheets["INFO"] = pd.DataFrame({"Komunikat": ["Brak danych do zapisu."]})

    return save_competition_results(out_path, sheets)

