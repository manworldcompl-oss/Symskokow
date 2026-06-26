# injury_batch.py
# ---------------------------------------------------------------
# Pomocnicze funkcje do zbiorczej obsługi kontuzji z całego tygodnia
# (wielu konkursów pod rząd). Nie zależą od Tkintera — operują na
# pandas.DataFrame i callbackach przekazanych z GUI.
# ---------------------------------------------------------------

from __future__ import annotations
import pandas as pd


def tag_falls_with_competition(falls_df: "pd.DataFrame | None", cycle_tag: str) -> "pd.DataFrame":
    """Dokłada kolumnę 'Zawody' = cycle_tag (np. 'WC-M') do falls_df
    z pojedynczego konkursu, żeby dało się je później pogrupować
    w zbiorczym dialogu tygodniowym. Zwraca pustą ramkę jeśli falls_df
    jest None/puste — bezpieczne do nieprzerwanego łączenia w pętli."""
    if falls_df is None or getattr(falls_df, "empty", True):
        return pd.DataFrame()
    out = falls_df.copy()
    out["Zawody"] = cycle_tag
    return out


def merge_week_falls(accum: list["pd.DataFrame"]) -> "pd.DataFrame":
    """Łączy listę DataFrame'ów (po jednym na konkurs) w jedną ramkę
    tygodniową. Pomija puste/None wpisy."""
    frames = [f for f in accum if isinstance(f, pd.DataFrame) and not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
