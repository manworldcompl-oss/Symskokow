"""
aktualizuj_klasyfikacje.py
--------------------------
Funkcja do podpięcia pod przycisk "Aktualizuj klasyfikacje" w GUI.

Wczytuje NAJNOWSZY plik Excel z folderu ./wyniki i aktualizuje tabelę
`statystyki_kariery` w bazie `manager_skokow.db`.

Nowe tabele (inicjalizowane przez init_nowe_tabele):
  - skocznie               (Kraj, Miasto, Skocznia, K, HS)
  - rekordy_skoczni        (id_skoczni, rekord_odl, zawodnik, kraj_zawodnika, sezon, plec)
  - nowe_rekordy_skoczni   (historia każdego nowego rekordu skoczni)
  - rekordy_swiata         (aktualny rekord świata osobno dla M i W)
  - nowe_rekordy_swiata    (historia każdego nowego rekordu świata)
  - rekordy_krajowe        (aktualny rekord krajowy dla M i W, 1 wiersz na kraj)
  - nowe_rekordy_krajowe   (historia każdego nowego rekordu krajowego)

Inicjalizacja tabel (wywołaj raz przy starcie aplikacji lub wbuduj w GUI):
    from aktualizuj_klasyfikacje import init_nowe_tabele
    init_nowe_tabele(
        db_path="manager_skokow.db",
        skocznie_csv="Skocznie_S51.csv",
        nations_csv="ALL_NATIONS.csv",
    )
"""

import sqlite3
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ── Mapowanie typ cyklu -> nazwa kolumny w bazie ──────────────────────────────
CYKL_DO_KOLUMNY = {
    "WC":    "wc",   "WC-M":  "wc",   "WC-W":  "wc",
    "COC":   "coc",  "COC-M": "coc",  "COC-W": "coc",
    "FC":    "fc",   "FC-M":  "fc",   "FC-W":  "fc",
    "GP":    "gp",   "GP-M":  "gp",   "GP-W":  "gp",
    "SCOC":  "scoc", "SCOC-M":"scoc", "SCOC-W":"scoc",
    "JC":    "jun",  "JC-M":  "jun",  "JC-W":  "jun",
    "JUN":   "jun",
    "MC":    "jun",  "MC-M":  "jun",  "MC-W":  "jun",
    "PC":    "jun",  "PC-M":  "jun",  "PC-W":  "jun",
    "QC":    "jun",  "QC-M":  "jun",  "QC-W":  "jun",
    "TC":    "jun",  "TC-M":  "jun",  "TC-W":  "jun",
    "AC":    "jun",  "AC-M":  "jun",  "AC-W":  "jun",
    "BC":    "jun",  "BC-M":  "jun",  "BC-W":  "jun",
    "DC":    "jun",  "DC-M":  "jun",  "DC-W":  "jun",
}


# ── Pomocnicze ────────────────────────────────────────────────────────────────

def _parse_distance(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace("~", "").replace(",", ".").strip())
    except ValueError:
        return 0.0


def _extract_hill_from_filename(filepath: str) -> str:
    stem  = Path(filepath).stem
    parts = stem.split("__")
    raw   = parts[0].strip() if parts else stem
    return raw.replace("_", " ")


def _find_newest_excel(folder: str) -> Path:
    folder_path = Path(folder)
    if not folder_path.exists():
        raise FileNotFoundError(
            f"Folder z wynikami nie istnieje: {folder_path.resolve()}\n"
            f"Utworz folder '{folder}' i wrzuc tam pliki xlsx z wynikami."
        )
    pliki = sorted(
        folder_path.glob("*.xlsx"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not pliki:
        raise FileNotFoundError(
            f"Brak plikow .xlsx w folderze: {folder_path.resolve()}"
        )
    return pliki[0]


def _best_distance_for_athlete(df_rounds: pd.DataFrame, zawodnik: str) -> float:
    rows = df_rounds[df_rounds["Zawodnik"] == zawodnik]
    if rows.empty:
        return 0.0
    distances = rows["Odleglosc (m)"].apply(
        lambda x: float(x) if pd.notna(x) else 0.0
    )
    return float(distances.max())


def _read_csv_any(path: str) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding=enc)
            if not df.empty:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def _count_records(cur, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    r = cur.fetchone()
    return int(r[0] if isinstance(r, (list, tuple)) else r["COUNT(*)"])


# ── Inicjalizacja nowych tabel ────────────────────────────────────────────────

def init_nowe_tabele(
    db_path: str = "manager_skokow.db",
    skocznie_csv: str = "Skocznie_S51.csv",
    nations_csv: str  = "ALL_NATIONS.csv",
):
    """
    Tworzy nowe tabele jesli nie istnieja i wypelnia:
      - skocznie         (z Skocznie_S51.csv)
      - rekordy_krajowe  (z ALL_NATIONS.csv)
    Pozostale tabele tworzy jako puste (wypelniane w trakcie aktualizacji).
    Bezpieczne do wielokrotnego wywolania (CREATE TABLE IF NOT EXISTS).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── 1. Skocznie ───────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS skocznie (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            kraj      TEXT,
            miasto    TEXT,
            skocznia  TEXT,
            k         INTEGER,
            hs        INTEGER
        )
    """)

    cur.execute("SELECT COUNT(*) FROM skocznie")
    if cur.fetchone()[0] == 0:
        # Szukaj CSV obok db jesli podana sciezka nie istnieje
        candidates = [skocznie_csv, str(Path(db_path).parent / skocznie_csv)]
        df_s = pd.DataFrame()
        for path in candidates:
            df_s = _read_csv_any(path)
            if not df_s.empty:
                break

        if not df_s.empty:
            col_kraj   = next((c for c in df_s.columns if c.upper() in ("KRAJ","REPREZENTACJA")), None)
            col_miasto = next((c for c in df_s.columns if c.upper() == "MIASTO"), None)
            col_skocz  = next((c for c in df_s.columns if c.upper() == "SKOCZNIA"), None)
            col_k      = next((c for c in df_s.columns if c.upper() == "K"), None)
            col_hs     = next((c for c in df_s.columns if c.upper() == "HS"), None)

            for _, row in df_s.iterrows():
                cur.execute(
                    "INSERT INTO skocznie (kraj, miasto, skocznia, k, hs) VALUES (?,?,?,?,?)",
                    (
                        str(row[col_kraj]).strip()   if col_kraj   else "",
                        str(row[col_miasto]).strip() if col_miasto else "",
                        str(row[col_skocz]).strip()  if col_skocz  else "",
                        int(row[col_k])  if col_k  and pd.notna(row[col_k])  else None,
                        int(row[col_hs]) if col_hs and pd.notna(row[col_hs]) else None,
                    )
                )
            log.info("Skocznie: wczytano %d wierszy z CSV.", len(df_s))
        else:
            log.warning("Nie znaleziono pliku Skocznie CSV: %s", skocznie_csv)

    # ── 2. Rekordy skoczni (biezace – max 1 rekord M + 1 W na skoczni) ───────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rekordy_skoczni (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            id_skoczni       INTEGER REFERENCES skocznie(id),
            rekord_odl       REAL,
            zawodnik         TEXT,
            kraj_zawodnika   TEXT,
            sezon            TEXT,
            plec             TEXT CHECK(plec IN ('M','W'))
        )
    """)

    # ── 3. Historia nowych rekordow skoczni ───────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nowe_rekordy_skoczni (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            id_skoczni       INTEGER REFERENCES skocznie(id),
            skocznia_nazwa   TEXT,
            rekord_odl       REAL,
            zawodnik         TEXT,
            kraj_zawodnika   TEXT,
            sezon            TEXT,
            plec             TEXT CHECK(plec IN ('M','W')),
            data_wpisu       TEXT DEFAULT (date('now'))
        )
    """)

    # ── 4. Rekordy swiata (biezace, 1 wiersz na plec) ─────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rekordy_swiata (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            rekord_odl       REAL,
            zawodnik         TEXT,
            kraj_zawodnika   TEXT,
            skocznia         TEXT,
            sezon            TEXT,
            plec             TEXT UNIQUE CHECK(plec IN ('M','W'))
        )
    """)

    # ── 5. Historia nowych rekordow swiata ────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nowe_rekordy_swiata (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            rekord_odl       REAL,
            zawodnik         TEXT,
            kraj_zawodnika   TEXT,
            skocznia         TEXT,
            sezon            TEXT,
            plec             TEXT CHECK(plec IN ('M','W')),
            data_wpisu       TEXT DEFAULT (date('now'))
        )
    """)

    # ── 6. Rekordy krajowe (biezace, 1 wiersz na kraj, kolumny M i W) ─────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rekordy_krajowe (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            reprezentacja TEXT,
            nat           TEXT UNIQUE,
            rekord_m      REAL,
            zawodnik_m    TEXT,
            skocznia_m    TEXT,
            sezon_m       TEXT,
            rekord_w      REAL,
            zawodnik_w    TEXT,
            skocznia_w    TEXT,
            sezon_w       TEXT
        )
    """)

    cur.execute("SELECT COUNT(*) FROM rekordy_krajowe")
    if cur.fetchone()[0] == 0:
        candidates = [nations_csv, str(Path(db_path).parent / nations_csv)]
        df_n = pd.DataFrame()
        for path in candidates:
            df_n = _read_csv_any(path)
            if not df_n.empty:
                break

        if not df_n.empty:
            col_repr = next((c for c in df_n.columns if c.upper() in ("KRAJ","REPREZENTACJA")), None)
            col_nat  = next((c for c in df_n.columns if c.upper() == "NAT"), None)
            for _, row in df_n.iterrows():
                cur.execute(
                    "INSERT OR IGNORE INTO rekordy_krajowe (reprezentacja, nat) VALUES (?, ?)",
                    (
                        str(row[col_repr]).strip() if col_repr else "",
                        str(row[col_nat]).strip()  if col_nat  else "",
                    )
                )
            log.info("Rekordy krajowe: zainicjalizowano %d krajow.", len(df_n))
        else:
            log.warning("Nie znaleziono pliku ALL_NATIONS CSV: %s", nations_csv)

    # ── 7. Historia nowych rekordow krajowych ─────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nowe_rekordy_krajowe (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            nat              TEXT,
            reprezentacja    TEXT,
            rekord_odl       REAL,
            zawodnik         TEXT,
            skocznia         TEXT,
            sezon            TEXT,
            plec             TEXT CHECK(plec IN ('M','W')),
            data_wpisu       TEXT DEFAULT (date('now'))
        )
    """)

    conn.commit()
    conn.close()
    log.info("init_nowe_tabele: wszystkie tabele gotowe.")


# ── Aktualizacja rekordow (skocznia / swiat / kraj) ───────────────────────────

def _aktualizuj_rekordy(cur, zawodnik, kraj_zawodnika, plec, best_dist, skocznia_nazwa, sezon):
    """
    Sprawdza i aktualizuje (jesli pobito):
      - rekord skoczni  -> rekordy_skoczni + nowe_rekordy_skoczni
      - rekord swiata   -> rekordy_swiata  + nowe_rekordy_swiata
      - rekord krajowy  -> rekordy_krajowe + nowe_rekordy_krajowe

    cur   – aktywny kursor sqlite3 (commit robi wywolujacy)
    Zwraca tuple (rek_skoczni_nowy, rek_swiata_nowy, rek_krajowy_nowy) jako bool.
    """
    if best_dist <= 0:
        return False, False, False

    plec = (plec or "M").strip().upper()[:1]
    if plec not in ("M", "W"):
        return False, False, False

    nowy_s, nowy_sw, nowy_k = False, False, False

    # ── a) Rekord skoczni ─────────────────────────────────────────────────────
    # Szukaj: 1) po nazwie skoczni dokladnie, 2) po miescie, 3) czesciowo
    cur.execute("SELECT id FROM skocznie WHERE LOWER(skocznia) = LOWER(?)", (skocznia_nazwa,))
    row_s = cur.fetchone()
    if row_s is None:
        cur.execute("SELECT id FROM skocznie WHERE LOWER(miasto) = LOWER(?)", (skocznia_nazwa,))
        row_s = cur.fetchone()
    if row_s is None:
        cur.execute(
            "SELECT id FROM skocznie WHERE"
            "  LOWER(?) LIKE '%' || LOWER(skocznia) || '%'"
            "  OR LOWER(skocznia) LIKE '%' || LOWER(?) || '%'"
            "  OR LOWER(?) LIKE '%' || LOWER(miasto) || '%'"
            "  OR LOWER(miasto) LIKE '%' || LOWER(?) || '%'",
            (skocznia_nazwa, skocznia_nazwa, skocznia_nazwa, skocznia_nazwa)
        )
        row_s = cur.fetchone()

    if row_s is not None:
        id_skoczni = row_s[0] if isinstance(row_s, (list, tuple)) else row_s["id"]
        cur.execute(
            "SELECT rekord_odl FROM rekordy_skoczni WHERE id_skoczni=? AND plec=?",
            (id_skoczni, plec)
        )
        rek_s   = cur.fetchone()
        stary_s = float(rek_s[0] if isinstance(rek_s, (list, tuple)) else rek_s["rekord_odl"]) if rek_s else 0.0

        if best_dist > stary_s:
            if rek_s:
                cur.execute(
                    """UPDATE rekordy_skoczni
                       SET rekord_odl=?, zawodnik=?, kraj_zawodnika=?, sezon=?
                       WHERE id_skoczni=? AND plec=?""",
                    (best_dist, zawodnik, kraj_zawodnika, sezon, id_skoczni, plec)
                )
            else:
                cur.execute(
                    """INSERT INTO rekordy_skoczni
                       (id_skoczni, rekord_odl, zawodnik, kraj_zawodnika, sezon, plec)
                       VALUES (?,?,?,?,?,?)""",
                    (id_skoczni, best_dist, zawodnik, kraj_zawodnika, sezon, plec)
                )
            cur.execute(
                """INSERT INTO nowe_rekordy_skoczni
                   (id_skoczni, skocznia_nazwa, rekord_odl, zawodnik, kraj_zawodnika, sezon, plec)
                   VALUES (?,?,?,?,?,?,?)""",
                (id_skoczni, skocznia_nazwa, best_dist, zawodnik, kraj_zawodnika, sezon, plec)
            )
            log.info("  NOWY REKORD SKOCZNI [%s][%s]: %.2f m — %s (%s)",
                     skocznia_nazwa, plec, best_dist, zawodnik, sezon)
            nowy_s = True

    # ── b) Rekord swiata ──────────────────────────────────────────────────────
    cur.execute("SELECT rekord_odl FROM rekordy_swiata WHERE plec=?", (plec,))
    rek_sw   = cur.fetchone()
    stary_sw = float(rek_sw[0] if isinstance(rek_sw, (list, tuple)) else rek_sw["rekord_odl"]) if rek_sw else 0.0

    if best_dist > stary_sw:
        if rek_sw:
            cur.execute(
                """UPDATE rekordy_swiata
                   SET rekord_odl=?, zawodnik=?, kraj_zawodnika=?, skocznia=?, sezon=?
                   WHERE plec=?""",
                (best_dist, zawodnik, kraj_zawodnika, skocznia_nazwa, sezon, plec)
            )
        else:
            cur.execute(
                """INSERT INTO rekordy_swiata
                   (rekord_odl, zawodnik, kraj_zawodnika, skocznia, sezon, plec)
                   VALUES (?,?,?,?,?,?)""",
                (best_dist, zawodnik, kraj_zawodnika, skocznia_nazwa, sezon, plec)
            )
        cur.execute(
            """INSERT INTO nowe_rekordy_swiata
               (rekord_odl, zawodnik, kraj_zawodnika, skocznia, sezon, plec)
               VALUES (?,?,?,?,?,?)""",
            (best_dist, zawodnik, kraj_zawodnika, skocznia_nazwa, sezon, plec)
        )
        log.info("  NOWY REKORD SWIATA [%s]: %.2f m — %s (%s, %s)",
                 plec, best_dist, zawodnik, skocznia_nazwa, sezon)
        nowy_sw = True

    # ── c) Rekord krajowy ─────────────────────────────────────────────────────
    nat = (kraj_zawodnika or "").strip().upper()
    if nat:
        cur.execute("SELECT * FROM rekordy_krajowe WHERE nat=?", (nat,))
        rek_k = cur.fetchone()

        if rek_k is None:
            cur.execute("INSERT INTO rekordy_krajowe (nat) VALUES (?)", (nat,))
            cur.execute("SELECT * FROM rekordy_krajowe WHERE nat=?", (nat,))
            rek_k = cur.fetchone()

        rek_k    = dict(rek_k)
        col_rek  = f"rekord_{plec.lower()}"
        col_zaw  = f"zawodnik_{plec.lower()}"
        col_skok = f"skocznia_{plec.lower()}"
        col_sez  = f"sezon_{plec.lower()}"

        stary_k = float(rek_k.get(col_rek) or 0.0)
        if best_dist > stary_k:
            cur.execute(
                f"""UPDATE rekordy_krajowe
                    SET {col_rek}=?, {col_zaw}=?, {col_skok}=?, {col_sez}=?
                    WHERE nat=?""",
                (best_dist, zawodnik, skocznia_nazwa, sezon, nat)
            )
            cur.execute(
                """INSERT INTO nowe_rekordy_krajowe
                   (nat, reprezentacja, rekord_odl, zawodnik, skocznia, sezon, plec)
                   VALUES (?,?,?,?,?,?,?)""",
                (nat, rek_k.get("reprezentacja", ""), best_dist,
                 zawodnik, skocznia_nazwa, sezon, plec)
            )
            log.info("  NOWY REKORD KRAJOWY [%s][%s]: %.2f m — %s (%s)",
                     nat, plec, best_dist, zawodnik, sezon)
            nowy_k = True

    return nowy_s, nowy_sw, nowy_k


# ── Glowna funkcja ────────────────────────────────────────────────────────────

def aktualizuj_najnowszy_wynik(
    sezon: str,
    typ_cyklu: str,
    wyniki_folder: str = "./wyniki",
    db_path: str = "manager_skokow.db",
) -> dict:
    """
    Wczytuje najnowszy plik Excel z folderu wyniki_folder i aktualizuje:
      - statystyki_kariery
      - rekordy_skoczni / nowe_rekordy_skoczni
      - rekordy_swiata  / nowe_rekordy_swiata
      - rekordy_krajowe / nowe_rekordy_krajowe
    """

    # ── Walidacja cyklu ───────────────────────────────────────────────────────
    typ_cyklu_norm = typ_cyklu.strip().upper()
    if typ_cyklu_norm not in CYKL_DO_KOLUMNY:
        dostepne = ", ".join(CYKL_DO_KOLUMNY.keys())
        raise ValueError(
            f"Nieznany typ cyklu '{typ_cyklu}'.\n"
            f"Dostepne wartosci: {dostepne}\n"
            f"Sprawdz pole 'Cykl' w zakladce Podglad wynikow."
        )
    kolumna = CYKL_DO_KOLUMNY[typ_cyklu_norm]

    # Plec z nazwy cyklu jako fallback
    plec_cyklu = "W" if typ_cyklu_norm.endswith("-W") else "M"

    # ── Upewnij sie, ze nowe tabele istnieja ──────────────────────────────────
    init_nowe_tabele(db_path=db_path)

    # ── Znajdz najnowszy plik ─────────────────────────────────────────────────
    excel_path = _find_newest_excel(wyniki_folder)
    skocznia   = _extract_hill_from_filename(str(excel_path))
    log.info("Najnowszy plik wynikow: %s", excel_path.name)
    log.info("Skocznia: %s | Cykl: %s | Sezon: %s", skocznia, typ_cyklu_norm, sezon)

    # ── Wczytaj arkusze ───────────────────────────────────────────────────────
    try:
        df_klasyfikacja = pd.read_excel(excel_path, sheet_name="Klasyfikacja")
        df_rundy        = pd.read_excel(excel_path, sheet_name="Konkurs - rundy")
    except Exception as e:
        raise RuntimeError(f"Blad wczytywania pliku '{excel_path.name}':\n{e}") from e

    df_klasyfikacja = df_klasyfikacja.dropna(subset=["Zawodnik"])
    df_rundy        = df_rundy.dropna(subset=["Zawodnik"])

    for wariant in ("Odleglosc (m)", "Odległość (m)", "Odl (m)", "dist_m"):
        if wariant in df_rundy.columns:
            df_rundy = df_rundy.rename(columns={wariant: "Odleglosc (m)"})
            break
    if "Odleglosc (m)" not in df_rundy.columns:
        num_cols = df_rundy.select_dtypes("number").columns.tolist()
        # Szukaj kolumny z wartosciami typowymi dla odleglosci (>30 m)
        best_col = None
        for c in num_cols:
            med = df_rundy[c].dropna().median()
            if pd.notna(med) and med > 30:
                best_col = c
                break
        if best_col:
            df_rundy = df_rundy.rename(columns={best_col: "Odleglosc (m)"})
        elif num_cols:
            df_rundy = df_rundy.rename(columns={num_cols[0]: "Odleglosc (m)"})

    if df_klasyfikacja.empty:
        raise ValueError(f"Arkusz 'Klasyfikacja' w pliku '{excel_path.name}' jest pusty.")

    log.info("Zawodnicy w klasyfikacji: %d", len(df_klasyfikacja))

    # ── Polacz z baza ─────────────────────────────────────────────────────────
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    raport = {
        "plik":                  excel_path.name,
        "skocznia":              skocznia,
        "zaktualizowano":        0,
        "nowi":                  0,
        "pominieci":             [],
        "nowe_rekordy_skoczni":  0,
        "nowe_rekordy_swiata":   0,
        "nowe_rekordy_krajowe":  0,
    }

    # ── Iteruj po zawodnikach z klasyfikacji ──────────────────────────────────
    for _, wiersz in df_klasyfikacja.iterrows():
        nazwa      = str(wiersz["Zawodnik"]).strip()
        miejsce    = int(wiersz["Miejsce"])      if pd.notna(wiersz.get("Miejsce"))    else None
        punkty_fis = float(wiersz["Punkty FIS"]) if pd.notna(wiersz.get("Punkty FIS")) else 0.0
        best_dist  = _best_distance_for_athlete(df_rundy, nazwa)

        # Szukaj zawodnika w bazie
        cur.execute(
            "SELECT id, kraj, \"płeć\" FROM zawodnicy WHERE zawodnik = ? COLLATE NOCASE",
            (nazwa,)
        )
        row = cur.fetchone()

        # Jesli brak kolumny 'plec', sprobuj z krzyzowaniem polskim znakiem

        if row is None:
            log.warning("Nie znaleziono w bazie: '%s' — pomijam.", nazwa)
            raport["pominieci"].append(nazwa)
            continue

        zawodnik_id    = row["id"]
        kraj_zawodnika = row["kraj"] or ""

        # Plec: z tabeli zawodnicy
        plec_zawodnika = plec_cyklu
        try:
            v = row["płeć"]
            if v and str(v).strip().upper()[:1] in ("M", "W"):
                plec_zawodnika = str(v).strip().upper()[:1]
        except Exception:
            pass

        # ── Statystyki kariery ────────────────────────────────────────────────
        cur.execute("SELECT * FROM statystyki_kariery WHERE zawodnik_id = ?", (zawodnik_id,))
        stat = cur.fetchone()

        if stat is None:
            cur.execute("INSERT INTO statystyki_kariery (zawodnik_id) VALUES (?)", (zawodnik_id,))
            conn.commit()
            cur.execute("SELECT * FROM statystyki_kariery WHERE zawodnik_id = ?", (zawodnik_id,))
            stat = cur.fetchone()
            raport["nowi"] += 1

        stat = dict(stat)

        nowe_lacznie     = (stat.get("konkursy_lacznie")    or 0)   + 1
        nowe_cykl        = (stat.get(f"konkursy_{kolumna}") or 0)   + 1
        nowe_pkt_lacznie = (stat.get("punkty_lacznie")      or 0.0) + punkty_fis
        nowe_pkt_cykl    = (stat.get(f"punkty_{kolumna}")   or 0.0) + punkty_fis

        stare_miejsce = stat.get(f"miejsce_{kolumna}") or 0
        if miejsce is not None:
            nowe_miejsce = miejsce if stare_miejsce == 0 else min(stare_miejsce, miejsce)
        else:
            nowe_miejsce = stare_miejsce

        stary_rekord = float(stat.get("rekord_odleglosc") or 0.0)
        if best_dist > stary_rekord:
            nowy_rekord          = best_dist
            nowy_rekord_skocznia = skocznia
            nowy_rekord_sezon    = str(sezon)
            log.info("  %s — NOWY REKORD OSOBISTY: %.2f m (%s, %s)",
                     nazwa, best_dist, skocznia, sezon)
        else:
            nowy_rekord          = stary_rekord
            nowy_rekord_skocznia = stat.get("rekord_skocznia") or "-"
            nowy_rekord_sezon    = stat.get("rekord_sezon")    or "-"

        cur.execute(f"""
            UPDATE statystyki_kariery SET
                konkursy_lacznie   = ?,
                konkursy_{kolumna} = ?,
                punkty_lacznie     = ?,
                punkty_{kolumna}   = ?,
                miejsce_{kolumna}  = ?,
                rekord_odleglosc   = ?,
                rekord_skocznia    = ?,
                rekord_sezon       = ?
            WHERE zawodnik_id = ?
        """, (
            nowe_lacznie, nowe_cykl,
            round(nowe_pkt_lacznie, 1), round(nowe_pkt_cykl, 1),
            nowe_miejsce,
            nowy_rekord, nowy_rekord_skocznia, nowy_rekord_sezon,
            zawodnik_id,
        ))

        # ── Rekordy (skocznia / swiat / kraj) ─────────────────────────────────
        if best_dist > 0:
            ns, nsw, nk = _aktualizuj_rekordy(
                cur=cur,
                zawodnik=nazwa,
                kraj_zawodnika=kraj_zawodnika,
                plec=plec_zawodnika,
                best_dist=best_dist,
                skocznia_nazwa=skocznia,
                sezon=sezon,
            )
            if ns:  raport["nowe_rekordy_skoczni"] += 1
            if nsw: raport["nowe_rekordy_swiata"]  += 1
            if nk:  raport["nowe_rekordy_krajowe"] += 1

        raport["zaktualizowano"] += 1
        log.info("  %-30s  miejsce=%-3s  pkt FIS=%6.1f  odl=%.2f m",
                 nazwa, miejsce, punkty_fis, best_dist)

    conn.commit()
    conn.close()

    log.info(
        "=== Gotowe! Zaktualizowano: %d | Nowi: %d | Pominieci: %d | "
        "Rek.skoczni: %d | Rek.swiata: %d | Rek.krajowe: %d ===",
        raport["zaktualizowano"], raport["nowi"], len(raport["pominieci"]),
        raport["nowe_rekordy_skoczni"], raport["nowe_rekordy_swiata"],
        raport["nowe_rekordy_krajowe"],
    )
    return raport


# ── Aktualizacja tylko rekordu zyciowego ──────────────────────────────────────

def aktualizuj_tylko_rekord(
    wyniki_folder: str = "./wyniki",
    db_path: str = "manager_skokow.db",
    sezon: str = "",
) -> dict:
    """
    Aktualizuje TYLKO rekord zyciowy zawodnikow (odleglosc, skocznia, sezon).
    Nie dotyka licznikow konkursow, punktow ani miejsc.
    Rowniez sprawdza rekordy skoczni / swiata / krajowe.
    """
    excel_path = _find_newest_excel(wyniki_folder)
    skocznia   = _extract_hill_from_filename(str(excel_path))

    try:
        df_rundy = pd.read_excel(excel_path, sheet_name="Konkurs - rundy")
    except Exception as e:
        raise RuntimeError(f"Blad wczytywania pliku '{excel_path.name}':\n{e}") from e

    df_rundy = df_rundy.dropna(subset=["Zawodnik"])
    for wariant in ("Odleglosc (m)", "Odległość (m)", "Odl (m)", "dist_m"):
        if wariant in df_rundy.columns:
            df_rundy = df_rundy.rename(columns={wariant: "Odleglosc (m)"})
            break

    init_nowe_tabele(db_path=db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    raport = {"plik": excel_path.name, "skocznia": skocznia, "zaktualizowano": 0, "pominieci": [], "nowe_rekordy_skoczni": 0, "nowe_rekordy_swiata": 0, "nowe_rekordy_krajowe": 0}

    zawodnicy = df_rundy["Zawodnik"].dropna().unique()
    for nazwa in zawodnicy:
        nazwa = str(nazwa).strip()
        best_dist = _best_distance_for_athlete(df_rundy, nazwa)
        if best_dist <= 0:
            continue

        cur.execute(
            "SELECT id, kraj, \"płeć\" FROM zawodnicy WHERE zawodnik = ? COLLATE NOCASE", (nazwa,)
        )
        row = cur.fetchone()
        if row is None:
            raport["pominieci"].append(nazwa)
            continue

        zawodnik_id    = row["id"]
        kraj_zawodnika = row["kraj"] or ""

        plec_zawodnika = "M"
        try:
            v = row["płeć"]
            if v and str(v).strip().upper()[:1] in ("M", "W"):
                plec_zawodnika = str(v).strip().upper()[:1]
        except Exception:
            pass

        cur.execute(
            "SELECT rekord_odleglosc, rekord_skocznia, rekord_sezon FROM statystyki_kariery WHERE zawodnik_id = ?",
            (zawodnik_id,)
        )
        stat = cur.fetchone()
        stary_rekord = float((stat and stat["rekord_odleglosc"]) or 0.0)

        if best_dist > stary_rekord:
            if stat is None:
                cur.execute(
                    "INSERT INTO statystyki_kariery (zawodnik_id, rekord_odleglosc, rekord_skocznia, rekord_sezon) VALUES (?, ?, ?, ?)",
                    (zawodnik_id, best_dist, skocznia, str(sezon))
                )
            else:
                cur.execute(
                    "UPDATE statystyki_kariery SET rekord_odleglosc=?, rekord_skocznia=?, rekord_sezon=? WHERE zawodnik_id=?",
                    (best_dist, skocznia, str(sezon), zawodnik_id)
                )
            raport["zaktualizowano"] += 1

        # Rekordy skoczni / swiata / krajowe — zawsze sprawdzaj
        ns, nsw, nk = _aktualizuj_rekordy(
            cur=cur,
            zawodnik=nazwa,
            kraj_zawodnika=kraj_zawodnika,
            plec=plec_zawodnika,
            best_dist=best_dist,
            skocznia_nazwa=skocznia,
            sezon=str(sezon),
        )
        if ns:  raport["nowe_rekordy_skoczni"] += 1
        if nsw: raport["nowe_rekordy_swiata"]  += 1
        if nk:  raport["nowe_rekordy_krajowe"] += 1

    conn.commit()
    conn.close()
    return raport
