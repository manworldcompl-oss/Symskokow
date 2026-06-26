# calendar_csv_resolver.py
# ---------------------------------------------------------------
# Resolver kalendarza Symskokow działający bezpośrednio na plikach
# Kalendarz_{sezon}_{CYKL}-{PŁEĆ}.csv generowanych przez
# SeasonPlannerFrame (calendars_gui_embedded.py).
#
# Zastępuje wcześniejszy, hipotetyczny calendar_resolver.py oparty
# na calendar_structure.json — to jest wersja zgodna z rzeczywistym
# źródłem danych używanym w grze.
#
# Format pliku (separator ';'):
#   WEEK;NAT;Skocznia;HS;Rodzaj;Dod. Inf.
#
# Moduł jest bezstanowy i nie zależy od Tkintera — operuje na
# pandas.DataFrame, więc można go testować w izolacji od GUI.
# ---------------------------------------------------------------

from __future__ import annotations
import glob
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


# Cykle, które w kolumnie "Rodzaj" mają specjalny, nie-wierszowy format
# (każdy wiersz to inna runda turnieju, a nie osobny dzień zawodów).
NKIC_CYCLE = "NKIC"
IST_CYCLE = "IST"

# SFWC: w CSV są 2 wiersze na płeć ("M - 1st day", "M - 2nd day"), ale
# to JEDEN konkurs per płeć (4 serie skoków w jednym przebiegu, cuts
# 40,30,30,30) — analogicznie do NKIC. Bierzemy tylko PIERWSZY wiersz
# danej płci, drugi ("2nd day") jest tym samym konkursem zapisanym
# powtórnie w CSV i jest ignorowany.
SFWC_CYCLE = "SFWC"

# Mistrzostwa: pliki Kalendarz_{sezon}_{TOUR}.csv BEZ sufiksu -M/-W —
# płeć (i dla niektórych: skocznia/kontynent) jest zakodowana wewnątrz
# kolumny "Dod. Inf.", a nie w nazwie pliku. Wszystkie te cykle są
# rozliczane przez panel "Mistrzostwa" (Zapisz Q/IND → CSV) zamiast
# zwykłej aktualizacji klasyfikacji (aktualizuj_najnowszy_wynik).
CHAMPIONSHIP_CYCLES = {"OG", "WCH", "SFWC", "UNI", "YOG", "COCH", "JWC", "NKIC", "IST"}

# Cykle z dwiema skoczniami (normalna h1 + duża h2) w obrębie jednego
# tygodnia — rozróżniane po HS wiersza, mapowane na _champs_hill_var.
_DUAL_HILL_CHAMPIONSHIPS = {"OG", "WCH"}
# Granica HS: normalna 85-109, duża 110-160 (zgodnie z RequirementsFrame).
_NORMAL_HS_MAX = 109

# Cykle, dla których panel Mistrzostw wymaga zaznaczenia checkboxa KO64
# (źródło wyniku to self._last_ko64_cls zamiast self._last_final_cls).
_KO64_CHAMPIONSHIPS = {"IST"}

# Rodzaje, które w tym GUI (symulator IND) są zawsze pomijane.
_SKIP_RODZAJ = {"TEAM", "MIXED"}

# Mapowanie wartości kolumny "Dod. Inf." (jak zapisuje je
# calendars_gui_embedded.py / SeasonPlannerFrame) na tour_code
# oczekiwany przez _update_tour_classification_from_preview w
# ski_jump_gui_full_embedded.py. Płeć rozstrzyga RAW AIR (M vs W) —
# bazujemy na cycle_tag, bo "RAW AIR" samo w sobie jest niejednoznaczne.
_DOD_INF_TO_TOUR_CODE = {
    "4HT": "TCS",
    "FNT": "FNT",  # FNT (WC-W, tydz.14) — 4 sesje: K1,K2 na 1. skoczni,
                   # K3,K4 na 2. skoczni. UWAGA: jeśli tour_schema w
                   # symulatorze (_update_tour_classification_from_preview)
                   # nie ma jeszcze zdefiniowanego schematu kolumn dla FNT,
                   # trzeba go tam dopisać: "FNT": ["K1","K2","K3","K4"].
    "NT": "NT",
    "FT": "FT",
    "BLUE BIRD": "BB",
    "P7": "PLANICA7",
    "W5": "WILLINGEN5",
    # "RAW AIR" obsługiwane osobno niżej (zależnie od płci cyklu)
}

# Turnieje, których PIERWSZY przebieg w tygodniu wymaga dodatkowego
# zapisu klasyfikacji KWALIFIKACJI jako sesja "Q1" (oprócz zwykłego "K1"
# dla samego konkursu). Zgodnie z tour_schema w symulatorze:
#   WILLINGEN5 / PLANICA7: ["Q1","K1","K2"]
# Q1 to kwalifikacje DO pierwszego konkursu (K1) — nie osobny wiersz/dzień
# w CSV, tylko dodatkowy zapis przy okazji pierwszego przebiegu.
_TOUR_CODES_WITH_Q1 = {"WILLINGEN5", "PLANICA7"}


def _resolve_tour_code(dod_inf: str, cycle_tag: str) -> str | None:
    """Zwraca tour_code dla danego wiersza/przebiegu na podstawie
    'Dod. Inf.' z CSV, albo None jeśli to nie jest sub-turniej."""
    tag = (dod_inf or "").strip().upper()
    if not tag:
        return None
    if tag == "RAW AIR":
        return "RAWAIR-W" if cycle_tag.upper().endswith("-W") else "RAWAIR-M"
    return _DOD_INF_TO_TOUR_CODE.get(tag)


@dataclass
class ChampionshipInfo:
    """Dane potrzebne do ustawienia panelu 'Mistrzostwa' w zakładce
    Podgląd (_champs_name_var/_champs_sex_var/_champs_type_var/
    _champs_hill_var/_champs_ko64_var) i wywołania _export_champs_results
    dla danego przebiegu mistrzostw.

    `name` to wartość _champs_name_var (np. "WCH", "OG", "COCH_EUROPE" —
    dla COCH dorzucamy kontynent z Dod. Inf., bo _cb_ch_name ma osobne
    wpisy COCH_EUROPE/COCH_ASIA/... w swojej liście wartości).
    `sex` to "M" lub "W" (_champs_sex_var).
    `hill` to "NORMAL"/"LARGE"/"" (_champs_hill_var) — puste dla cykli
    z jedną skocznią (SFWC, JWC, YOG, UNI, NKIC, IST, COCH).
    `ko64` to True tylko dla IST (_champs_ko64_var) — źródłem wyniku
    jest wtedy self._last_ko64_cls zamiast self._last_final_cls.
    """
    name: str
    sex: str
    hill: str = ""
    ko64: bool = False


@dataclass
class CompetitionRun:
    """Jeden konkretny przebieg symulacji do uruchomienia.

    `cycle_tag` to etykieta zgodna z Twoim var_cycle, np. "WC-M", "NKIC-M".
    `nat`, `skocznia`, `hs` pochodzą z wiersza/bloku CSV.
    `mode` to jedno z: "classic", "ko50", "ko64" — mówi które pole
    trybu (var_classic/var_ko50/var_ko64_full) ustawić w GUI.
    `format_preset` to opcjonalna etykieta presetu formatu (np. dla
    NKIC: "NKIC  (64,32,16,8,4,2 / Q:64)"), żeby ustawić właściwe cuts.
    `dod_inf` to dodatkowy opis z kolumny "Dod. Inf." (RAW AIR, FT, ...).
    `tour_code` to kod sub-turnieju wyliczony z dod_inf (np. "TCS", "FNT",
    "RAWAIR-M") zgodny z tour_code oczekiwanym przez
    _update_tour_classification_from_preview w symulatorze — None jeśli
    ten przebieg nie należy do żadnego sub-turnieju.
    `needs_q1_first` to True wyłącznie dla PIERWSZEGO przebiegu danego
    tour_code w tygodniu, gdy ten turniej wymaga sesji "Q1" przed "K1"
    (PLANICA7/WILLINGEN5) — Q1 to kwalifikacje DO pierwszego konkursu,
    więc dotyczy tylko startu turnieju, nie każdej sesji.
    `champ_info` jest ustawione zamiast tour_code, gdy ten przebieg
    należy do mistrzostw (OG/WCH/SFWC/UNI/YOG/COCH/JWC/NKIC/IST) — woła
    się wtedy panel Mistrzostw (Zapisz Q→CSV + Zapisz IND→CSV) zamiast
    aktualizuj_najnowszy_wynik. tour_code i champ_info wzajemnie się
    wykluczają.
    `row_indices` to indeksy wierszy źródłowego DataFrame, które złożyły
    się na ten przebieg (przydatne do debugowania/logu).
    """
    cycle_tag: str
    nat: str
    skocznia: str
    hs: str
    mode: str
    format_preset: str | None
    dod_inf: str
    tour_code: str | None = None
    needs_q1_first: bool = False
    champ_info: ChampionshipInfo | None = None
    row_indices: list[int] = field(default_factory=list)

    def label(self) -> str:
        extra = f" [{self.dod_inf}]" if self.dod_inf else ""
        tour = ""
        if self.tour_code:
            tour = f" (turniej: {self.tour_code}{'+Q1' if self.needs_q1_first else ''})"
        if self.champ_info:
            ci = self.champ_info
            hill_part = f"/{ci.hill}" if ci.hill else ""
            ko64_part = "+KO64" if ci.ko64 else ""
            tour = f" (mistrzostwa: {ci.name}-{ci.sex}{hill_part}{ko64_part})"
        return f"{self.cycle_tag} @ {self.skocznia} (HS{self.hs}){extra}{tour}"


@dataclass
class WeekResolution:
    week: int
    season: str
    runs: list[CompetitionRun]
    skipped: list[str]  # opisy pominiętych wierszy (TEAM/MIXED)

    def summary_line(self) -> str:
        labels = ", ".join(r.label() for r in self.runs)
        return (
            f"Tydzień {self.week} (sezon {self.season}): "
            f"{len(self.runs)} przebiegów symulacji do uruchomienia: {labels or '(brak)'}"
        )


def _read_calendar_csv(path: Path) -> pd.DataFrame:
    """Czyta pojedynczy plik Kalendarz_*.csv, z fallbackiem kodowania
    analogicznym do istniejącego _load_calendars_dir w GUI."""
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
        try:
            df = pd.read_csv(path, sep=";", encoding=enc)
            return df
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Nie mogę wczytać kalendarza: {path}\n{last_err}")


def _cycle_tag_from_filename(path: Path) -> str:
    """'Kalendarz_S51_WC-M.csv' -> 'WC-M'. Wymaga >=3 części po '_'."""
    stem = path.stem  # "Kalendarz_S51_WC-M"
    parts = stem.split("_")
    if len(parts) >= 3:
        return parts[-1]
    return stem


def _normalize_week_col(df: pd.DataFrame) -> pd.DataFrame:
    """Ujednolica nazwę kolumny tygodnia do 'WEEK' niezależnie od
    wielkości liter w nagłówku pliku (np. 'Week' z calendars_gui)."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        if c.upper() == "WEEK":
            rename[c] = "WEEK"
    if rename:
        df = df.rename(columns=rename)
    if "WEEK" in df.columns:
        df["WEEK"] = pd.to_numeric(df["WEEK"], errors="coerce")
    return df


def _base_cycle(cycle_tag: str) -> str:
    """'WC-M' -> 'WC'; 'NKIC-M' -> 'NKIC'."""
    return re.sub(r"-(?:M|W)$", "", cycle_tag.strip().upper())


def _hs_numeric(hs_val) -> str:
    """'HS140' / '140' / 140 -> '140' (sam numer jako string, do dociągania K)."""
    s = str(hs_val or "").strip().upper()
    s = s.replace("HS", "").strip()
    return s


def _hill_class_for_hs(hs_str: str) -> str:
    """Klasyfikuje HS na 'NORMAL' (85-109) / 'LARGE' (110-160) / ''
    (poza zakresem lub brak danych) — używane dla OG/WCH, które mają
    dwie skocznie w jednym tygodniu."""
    try:
        hs = float(hs_str)
    except (TypeError, ValueError):
        return ""
    if 85 <= hs <= _NORMAL_HS_MAX:
        return "NORMAL"
    if hs > _NORMAL_HS_MAX:
        return "LARGE"
    return ""


def _parse_champ_sex(dod_inf: str) -> str:
    """Wyciąga płeć z 'Dod. Inf.' niezależnie od dialektu:
    'M' / 'W' (WCH,OG,JWC,YOG,UNI) / 'M - 1st day' / 'W - Europe'
    (SFWC, COCH) / 'MEN' / 'WOMEN' (NKIC, IST). Zwraca 'M' albo 'W'."""
    tag = (dod_inf or "").strip().upper()
    first_token = re.split(r"[\s\-]+", tag)[0] if tag else ""
    if first_token in ("M", "MEN"):
        return "M"
    if first_token in ("W", "WOMEN"):
        return "W"
    # fallback: szukaj W/M gdziekolwiek (na wszelki wypadek przy
    # nietypowym formacie) — wolimy zgadnąć niż wywrócić cały resolver
    if "WOMEN" in tag or tag.startswith("W"):
        return "W"
    return "M"


def _parse_coch_continent(dod_inf: str) -> str:
    """'W - Europe' -> 'Europe'; brak myślnika -> ''."""
    if "-" not in (dod_inf or ""):
        return ""
    return dod_inf.split("-", 1)[1].strip()


# Mapowanie pełnej nazwy kontynentu (jak w Dod. Inf. dla COCH) na
# wartość oczekiwaną przez _cb_ch_name w panelu Mistrzostw
# ("COCH_EUROPE", "COCH_ASIA", "COCH_NORTHAMERICA", ...).
_COCH_CONTINENT_TO_CHAMPS_NAME = {
    "EUROPE": "COCH_EUROPE",
    "ASIA": "COCH_ASIA",
    "NORTH AMERICA": "COCH_NORTHAMERICA",
    "SOUTH AMERICA": "COCH_SOUTHAMERICA",
    "AFRICA": "COCH_AFRICA",
    "OCEANIA": "COCH_OCEANIA",
}

# Mapowanie pełnej nazwy kontynentu na SKRÓT używany w var_cycle/_CYCLES
# w ski_jump_gui_full_embedded.py ("COCH-EU-M", "COCH-AS-W", ...) — to
# INNY format niż _cb_ch_name powyżej; _on_cycle_selected (lista startowa,
# auto-setup skoczni) potrzebuje właśnie tego skrótu, nie pełnej nazwy.
_COCH_CONTINENT_TO_CYCLE_SUFFIX = {
    "EUROPE": "EU",
    "ASIA": "AS",
    "NORTH AMERICA": "NA",
    "SOUTH AMERICA": "SA",
    "AFRICA": "AF",
    "OCEANIA": "OC",
}


def _champs_name_for_cycle(base_cycle: str, continent: str = "") -> str:
    """Zwraca wartość do _champs_name_var. Dla COCH wymaga kontynentu
    (z Dod. Inf.) i mapuje go na "COCH_<KONTYNENT>" zgodnie z listą
    wartości w comboboxie _cb_ch_name."""
    if base_cycle == "COCH":
        return _COCH_CONTINENT_TO_CHAMPS_NAME.get(continent.strip().upper(), "COCH_EUROPE")
    return base_cycle


def _cycle_tag_for_cycle(base_cycle: str, sex: str, continent: str = "") -> str:
    """Zwraca cycle_tag zgodny z var_cycle/_CYCLES w
    ski_jump_gui_full_embedded.py (do _on_cycle_selected — lista
    startowa, auto-setup skoczni). Dla COCH to SKRÓT kontynentu
    ("COCH-EU-M"), INNY niż champs_name ("COCH_EUROPE") używane w
    panelu Mistrzostw — te dwa identyfikatory celowo się różnią, bo
    służą dwóm różnym, niezależnym mechanizmom w GUI."""
    if base_cycle == "COCH":
        suffix = _COCH_CONTINENT_TO_CYCLE_SUFFIX.get(continent.strip().upper(), "EU")
        return f"COCH-{suffix}-{sex}"
    return f"{base_cycle}-{sex}"


def resolve_week_from_calendars(
    calendars_dir: str | Path,
    week: int,
    season: str,
    nkic_format_preset: str = "NKIC  (64,32,16,8,4,2 / Q:64)",
    sfwc_format_preset: str = "SFWC  (40,30,30,30 / Q:40)",
) -> WeekResolution:
    """Główna funkcja resolvera CSV.

    `calendars_dir` to folder z plikami Kalendarz_{season}_{CYKL}.csv
    (Twój istniejący var_calendars_dir).
    `season` to string w stylu "S51" (musi zgadzać się z nazwami plików,
    bo nazwa pliku zawiera sezon — w przeciwieństwie do resolvera JSON,
    tu nie liczymy offsetów mod4/mod2, tylko czytamy gotowe pliki).
    """
    calendars_dir = Path(calendars_dir)
    pattern = str(calendars_dir / f"Kalendarz_{season}_*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        # fallback: czasem pliki są bez podkreślnika po "Kalendarz" lub
        # z inną wielkością liter w prefiksie — spróbuj ogólnego glob
        files = sorted(glob.glob(str(calendars_dir / "Kalendarz_*.csv")))
        files = [f for f in files if f"_{season}_" in os.path.basename(f)]

    if not files:
        raise ValueError(
            f"Brak plików kalendarza dla sezonu {season} w folderze {calendars_dir}"
        )

    runs: list[CompetitionRun] = []
    skipped: list[str] = []

    for fpath in files:
        path = Path(fpath)
        cycle_tag = _cycle_tag_from_filename(path)
        base = _base_cycle(cycle_tag)

        try:
            df = _read_calendar_csv(path)
            df = _normalize_week_col(df)
        except Exception as e:
            skipped.append(f"{cycle_tag} (błąd odczytu: {e})")
            continue

        if "WEEK" not in df.columns:
            skipped.append(f"{cycle_tag} (brak kolumny WEEK)")
            continue

        week_df = df[df["WEEK"] == float(week)].copy()
        if week_df.empty:
            continue

        # Ujednolicenie nazw kolumn opisowych (Dod. Inf. / Dod. inf.)
        rodzaj_col = next((c for c in week_df.columns if c.strip().lower() == "rodzaj"), None)
        nat_col = next((c for c in week_df.columns if c.strip().upper() == "NAT"), None)
        skocznia_col = next((c for c in week_df.columns if c.strip().lower() == "skocznia"), None)
        hs_col = next((c for c in week_df.columns if c.strip().upper() == "HS"), None)
        info_col = next((c for c in week_df.columns if "DOD" in c.strip().upper()), None)

        def _val(row, col):
            if col is None:
                return ""
            v = row.get(col, "")
            return "" if pd.isna(v) else str(v).strip()

        # ---- mistrzostwa: NKIC i SFWC (jeden zgrupowany przebieg per płeć) ----
        if base == NKIC_CYCLE:
            # Cały blok wierszy danej PŁCI w tym tygodniu = jeden przebieg
            # (poszczególne "Round 1/64" itd. są tylko informacyjne).
            # Dod. Inf. niesie tu "MEN"/"WOMEN" — grupujemy po nim, żeby
            # nie zlać zawodników obu płci w jeden przebieg.
            week_df["_sex"] = week_df.apply(lambda r: _parse_champ_sex(_val(r, info_col)), axis=1)
            for sex_val, sub in week_df.groupby("_sex", sort=True):
                first = sub.iloc[0]
                runs.append(
                    CompetitionRun(
                        cycle_tag=f"{base}-{sex_val}",
                        nat=_val(first, nat_col),
                        skocznia=_val(first, skocznia_col),
                        hs=_hs_numeric(_val(first, hs_col)),
                        mode="classic",
                        format_preset=nkic_format_preset,
                        dod_inf=_val(first, info_col),
                        champ_info=ChampionshipInfo(name=base, sex=sex_val, hill="", ko64=False),
                        row_indices=list(sub.index),
                    )
                )
            continue

        if base == SFWC_CYCLE:
            # Tylko wiersze Rodzaj=IND (TEAM/MIXED odfiltrowane jak zwykle).
            # CSV ma 2 wiersze na płeć ("M - 1st day", "M - 2nd day") — to
            # ten sam, jeden konkurs (4 serie w jednym przebiegu, cuts
            # 40,30,30,30), więc bierzemy tylko PIERWSZY wiersz danej płci
            # w kolejności występowania; drugi jest ignorowany.
            ind_mask = week_df.apply(
                lambda r: (_val(r, rodzaj_col).upper() or "IND") == "IND", axis=1
            )
            skipped_team = week_df[~ind_mask]
            for _, srow in skipped_team.iterrows():
                skipped.append(f"{base} @ {_val(srow, skocznia_col)} (TEAM)")

            ind_df = week_df[ind_mask].copy()
            ind_df["_sex"] = ind_df.apply(lambda r: _parse_champ_sex(_val(r, info_col)), axis=1)
            seen_sex: set[str] = set()
            for _, row in ind_df.iterrows():
                sex_val = row["_sex"]
                if sex_val in seen_sex:
                    skipped.append(f"{base}-{sex_val} @ {_val(row, skocznia_col)} (duplikat dnia, pominięty)")
                    continue
                seen_sex.add(sex_val)
                runs.append(
                    CompetitionRun(
                        cycle_tag=f"{base}-{sex_val}",
                        nat=_val(row, nat_col),
                        skocznia=_val(row, skocznia_col),
                        hs=_hs_numeric(_val(row, hs_col)),
                        mode="classic",
                        format_preset=sfwc_format_preset,
                        dod_inf=_val(row, info_col),
                        champ_info=ChampionshipInfo(name=base, sex=sex_val, hill="", ko64=False),
                        row_indices=[row.name],
                    )
                )
            continue

        # ---- mistrzostwa: IST (specjalny format rundowy, KO64) ----
        if base == IST_CYCLE:
            # Grupowanie po (skocznia HS, płeć) — każda kombinacja to
            # jeden przebieg KO64. IST może mieć 2 skocznie (duża+normalna)
            # x 2 płcie = do 4 przebiegów.
            week_df["_hs_norm"] = week_df.apply(lambda r: _hs_numeric(_val(r, hs_col)), axis=1)
            week_df["_sex"] = week_df.apply(lambda r: _parse_champ_sex(_val(r, info_col)), axis=1)
            for (hs_val, sex_val), sub in week_df.groupby(["_hs_norm", "_sex"], sort=True):
                first = sub.iloc[0]
                runs.append(
                    CompetitionRun(
                        cycle_tag=f"{base}-{sex_val}",
                        nat=_val(first, nat_col),
                        skocznia=_val(first, skocznia_col),
                        hs=hs_val,
                        mode="ko64",
                        format_preset=None,
                        dod_inf=_val(first, info_col),
                        champ_info=ChampionshipInfo(name=base, sex=sex_val, hill="", ko64=True),
                        row_indices=list(sub.index),
                    )
                )
            continue

        # ---- mistrzostwa: OG, WCH, UNI, YOG, COCH, JWC ----
        # Format wierszowy jak zwykłe cykle (Rodzaj=IND/TEAM/MIXED), ale
        # płeć (i dla COCH: kontynent) jest w Dod. Inf., a plik nie ma
        # sufiksu -M/-W w nazwie. Każdy wiersz IND to osobny przebieg
        # (dla OG/WCH to 2 wiersze na płeć — normalna+duża skocznia; dla
        # JWC/YOG/UNI to 1 wiersz na płeć; dla COCH to 1 wiersz na płeć
        # na kontynent). SFWC i NKIC mają własne, wcześniejsze gałęzie
        # (jeden zgrupowany przebieg per płeć) i tu już nie trafiają.
        if base in CHAMPIONSHIP_CYCLES:  # tu: OG, WCH, UNI, YOG, COCH, JWC
            for idx, row in week_df.iterrows():
                rodzaj = _val(row, rodzaj_col).upper() or "IND"
                info_raw = _val(row, info_col)

                if rodzaj in _SKIP_RODZAJ:
                    skipped.append(f"{base} @ {_val(row, skocznia_col)} ({rodzaj})")
                    continue
                if rodzaj != "IND":
                    skipped.append(f"{base} @ {_val(row, skocznia_col)} (nieobsłużony Rodzaj='{rodzaj}')")
                    continue

                sex_val = _parse_champ_sex(info_raw)
                hs_str = _hs_numeric(_val(row, hs_col))
                hill = _hill_class_for_hs(hs_str) if base in _DUAL_HILL_CHAMPIONSHIPS else ""
                continent = _parse_coch_continent(info_raw) if base == "COCH" else ""
                champs_name = _champs_name_for_cycle(base, continent)
                cycle_tag_for_run = _cycle_tag_for_cycle(base, sex_val, continent)

                runs.append(
                    CompetitionRun(
                        cycle_tag=cycle_tag_for_run,
                        nat=_val(row, nat_col),
                        skocznia=_val(row, skocznia_col),
                        hs=hs_str,
                        mode="classic",
                        format_preset=None,
                        dod_inf=info_raw,
                        champ_info=ChampionshipInfo(name=champs_name, sex=sex_val, hill=hill, ko64=False),
                        row_indices=[idx],
                    )
                )
            continue

        # ---- zwykłe cykle (WC, COC, FC, GP, SCOC, JC...): każdy wiersz to osobny przebieg ----
        for idx, row in week_df.iterrows():
            rodzaj = _val(row, rodzaj_col).upper() or "IND"

            if rodzaj in _SKIP_RODZAJ:
                skipped.append(f"{cycle_tag} @ {_val(row, skocznia_col)} ({rodzaj})")
                continue

            if rodzaj == "KO50":
                mode = "ko50"
            elif rodzaj == "KO64":
                mode = "ko64"
            elif rodzaj == "IND":
                mode = "classic"
            else:
                # nieznany/rundowy format (np. zaszłość z innego cyklu) —
                # nie ryzykujemy złego uruchomienia, pomijamy z adnotacją
                skipped.append(f"{cycle_tag} @ {_val(row, skocznia_col)} (nieobsłużony Rodzaj='{rodzaj}')")
                continue

            runs.append(
                CompetitionRun(
                    cycle_tag=cycle_tag,
                    nat=_val(row, nat_col),
                    skocznia=_val(row, skocznia_col),
                    hs=_hs_numeric(_val(row, hs_col)),
                    mode=mode,
                    format_preset=None,
                    dod_inf=_val(row, info_col),
                    tour_code=_resolve_tour_code(_val(row, info_col), cycle_tag),
                    row_indices=[idx],
                )
            )

    # Post-processing: oznacz PIERWSZY przebieg każdego tour_code z
    # _TOUR_CODES_WITH_Q1 jako wymagający dodatkowego zapisu sesji "Q1"
    # (kwalifikacje do pierwszego konkursu turnieju). Robimy to na
    # zebranej liście `runs`, więc kolejność jest zgodna z faktyczną
    # kolejnością rozgrywania (a nie z przypadkową kolejnością plików
    # zwracaną przez glob).
    seen_tour_codes: set[str] = set()
    for run in runs:
        if run.tour_code in _TOUR_CODES_WITH_Q1 and run.tour_code not in seen_tour_codes:
            run.needs_q1_first = True
            seen_tour_codes.add(run.tour_code)

    return WeekResolution(week=week, season=season, runs=runs, skipped=skipped)


# ---------------------------------------------------------------
# Mini-test manualny:
#   python calendar_csv_resolver.py <folder_kalendarzy> <sezon, np. S51> <tydzień>
# ---------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Użycie: python calendar_csv_resolver.py <folder> <sezon> <tydzień>")
        sys.exit(1)

    folder, season, week_str = sys.argv[1], sys.argv[2], sys.argv[3]
    res = resolve_week_from_calendars(folder, int(week_str), season)
    print(res.summary_line())
    for r in res.runs:
        preset = f" preset={r.format_preset!r}" if r.format_preset else ""
        print(f"  - [{r.mode}]{preset} {r.label()}  (wiersze CSV: {r.row_indices})")
    if res.skipped:
        print("Pominięte:")
        for s in res.skipped:
            print(f"  - {s}")
