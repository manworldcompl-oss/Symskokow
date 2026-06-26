from __future__ import annotations
import re
import os
import csv
import pandas as pd
import dearpygui.dearpygui as dpg
from pathlib import Path

# ---------------------------------------------------------------------------
# KONFIGURACJA
# ---------------------------------------------------------------------------
DEFAULT_CANDIDATES = [
    Path("./S51/Finanse S51.csv"),
    Path("Finanse S51.csv"),
]

SEP_COLS = {1, 3, 7, 10, 12, 14, 16, 19, 21, 23, 24, 26}  # separatory grup kolumn
CONTINENT_COLOR = {
    # Europa
    "ALB":"AL","AND":"AD","AUT":"AT","BEL":"BE","BLR":"BY","BIH":"BA","BUL":"BG",
    "CRO":"HR","MNE":"ME","CZE":"CZ","DEN":"DK","EST":"EE","FIN":"FI","FRA":"FR",
    "GIB":"GI","GRE":"GR","ESP":"ES","NED":"NL","IRL":"IE","ISL":"IS","KOS":"XK",
    "LIE":"LI","LTU":"LT","LUX":"LU","LAT":"LV","MKD":"MK","MLT":"MT","MDA":"MD",
    "MON":"MC","GER":"DE","NOR":"NO","POL":"PL","POR":"PT","RUS":"RU","ROU":"RO",
    "SMR":"SM","SRB":"RS","SVK":"SK","SLO":"SI","SUI":"CH","SWE":"SE","UKR":"UA",
    "HUN":"HU","GBR":"GB","ITA":"IT","FRO":"FO",
}

IOC_TO_ISO2 = {
    "ALB":"AL","AND":"AD","AUT":"AT","BEL":"BE","BLR":"BY","BIH":"BA","BUL":"BG",
    "CRO":"HR","MNE":"ME","CZE":"CZ","DEN":"DK","EST":"EE","FIN":"FI","FRA":"FR",
    "GIB":"GI","GRE":"GR","ESP":"ES","NED":"NL","IRL":"IE","ISL":"IS","KOS":"XK",
    "LIE":"LI","LTU":"LT","LUX":"LU","LAT":"LV","MKD":"MK","MLT":"MT","MDA":"MD",
    "MON":"MC","GER":"DE","NOR":"NO","POL":"PL","POR":"PT","RUS":"RU","ROU":"RO",
    "SMR":"SM","SRB":"RS","SVK":"SK","SLO":"SI","SUI":"CH","SWE":"SE","UKR":"UA",
    "HUN":"HU","GBR":"GB","ITA":"IT","FRO":"FO","AFG":"AF","KSA":"SA","ARM":"AM",
    "AZE":"AZ","BRN":"BH","BAN":"BD","BHU":"BT","CHN":"CN","CYP":"CY","PHI":"PH",
    "GEO":"GE","HKG":"HK","IND":"IN","INA":"ID","IRI":"IR","IRQ":"IQ","ISR":"IL",
    "JPN":"JP","YEM":"YE","QAT":"QA","KAZ":"KZ","KGZ":"KG","KOR":"KR","LAO":"LA",
    "MAS":"MY","MYA":"MM","MGL":"MN","NEP":"NP","PAK":"PK","SIN":"SG","SRI":"LK",
    "TJK":"TJ","THA":"TH","TPE":"TW","TUR":"TR","UZB":"UZ","VIE":"VN","UAE":"AE",
    "ARG":"AR","BOL":"BO","BRA":"BR","CHI":"CL","ECU":"EC","GUY":"GY","COL":"CO",
    "PAR":"PY","PER":"PE","SUR":"SR","URU":"UY","VEN":"VE","BAH":"BS","BAR":"BB",
    "BIZ":"BZ","BER":"BM","CUW":"CW","DMA":"DM","DOM":"DO","GRL":"GL","GUA":"GT",
    "HAI":"HT","HON":"HN","JAM":"JM","CAN":"CA","CRC":"CR","CUB":"CU","MEX":"MX",
    "NCA":"NI","PAN":"PA","PUR":"PR","ESA":"SV","SKN":"KN","LCA":"LC","USA":"US",
    "TRI":"TT","ALG":"DZ","BUR":"BF","CHA":"TD","COD":"CD","EGY":"EG","ETH":"ET",
    "GHA":"GH","GUI":"GN","GBS":"GW","CMR":"CM","KEN":"KE","LBA":"LY","MAD":"MG",
    "MLI":"ML","MAR":"MA","MOZ":"MZ","NAM":"NA","NGR":"NG","RPA":"ZA","CPV":"CV",
    "RWA":"RW","SEN":"SN","SLE":"SL","SOM":"SO","SUD":"SD","TAN":"TZ","TUN":"TN",
    "UGA":"UG","CIV":"CI","AUS":"AU","FIJ":"FJ","KIR":"KI","FSM":"FM","NRU":"NR",
    "NZL":"NZ","PLW":"PW","PNG":"PG","SAM":"WS","TGA":"TO","TUV":"TV","VAN":"VU",
    "COK":"CK","MHL":"MH","SOL":"SB",
}

# Kontynenty -> kolor tła (R,G,B,A)
IOC_CONTINENT = {
    **{k: "EU" for k in ["ALB","AND","AUT","BEL","BLR","BIH","BUL","CRO","MNE","CZE",
       "DEN","EST","FIN","FRA","GIB","GRE","ESP","NED","IRL","ISL","KOS","LIE","LTU",
       "LUX","LAT","MKD","MLT","MDA","MON","GER","NOR","POL","POR","RUS","ROU","SMR",
       "SRB","SVK","SLO","SUI","SWE","UKR","HUN","GBR","ITA","FRO"]},
    **{k: "AS" for k in ["AFG","KSA","ARM","AZE","BRN","BAN","BHU","CHN","PHI","GEO",
       "HKG","IND","INA","IRI","IRQ","ISR","JPN","YEM","QAT","KAZ","KGZ","KOR","LAO",
       "MAS","MYA","MGL","NEP","PAK","SIN","SRI","TJK","THA","TPE","TUR","UZB","VIE",
       "UAE","CYP"]},
    # Ameryka Północna i Środkowa
    **{k: "AN" for k in ["CAN","USA","MEX","GUA","BIZ","HON","ESA","NCA","CRC","PAN",
       "CUB","JAM","HAI","DOM","PUR","BAH","BAR","TRI","DMA","SKN","LCA","BER","CUW",
       "GRL"]},
    # Ameryka Południowa
    **{k: "AS_" for k in ["ARG","BOL","BRA","CHI","ECU","GUY","COL","PAR","PER","SUR",
       "URU","VEN"]},
    **{k: "AF" for k in ["ALG","BUR","CHA","COD","EGY","ETH","GHA","GUI","GBS","CMR",
       "KEN","LBA","MAD","MLI","MAR","MOZ","NAM","NGR","RPA","CPV","RWA","SEN","SLE",
       "SOM","SUD","TAN","TUN","UGA","CIV"]},
    **{k: "OC" for k in ["AUS","FIJ","KIR","FSM","NRU","NZL","PLW","PNG","SAM","TGA",
       "TUV","VAN","COK","MHL","SOL"]},
}

CONTINENT_COLORS = {
    "EU": (100, 140, 255, 255),    # niebieski       — Europa
    "AS": (255, 200,  80, 255),    # żółty           — Azja
    "AN": ( 80, 200, 120, 255),    # zielony jasny   — Ameryka Północna
    "AS_":(  0, 160,  80, 255),    # zielony ciemny  — Ameryka Południowa
    "AF": (240, 140,  60, 255),    # pomarańczowy    — Afryka
    "OC": (180, 100, 240, 255),    # fioletowy       — Oceania
}

def get_flag(ioc_code: str) -> str:
    """Zwraca prefix [KOD] dla danego kraju."""
    code = ioc_code.upper().strip()
    return f"[{code}] " if code else ""


def get_country_color(ioc_code: str):
    """Zwraca kolor (R,G,B,A) dla danego kraju wg kontynentu."""
    continent = IOC_CONTINENT.get(ioc_code.upper(), "EU")
    return CONTINENT_COLORS.get(continent, (200, 200, 200, 255))

# ---------------------------------------------------------------------------
# STAN GLOBALNY
# ---------------------------------------------------------------------------
state = {
    "df": pd.DataFrame(),
    "df_view": pd.DataFrame(),
    "path": "",
    "sort_col": -1,
    "sort_asc": True,
    "sort_keys": [],
    "filter_text": "",
    "row_tags": [],
    "cell_tags": [],
    "col_tags": [],
    "col_names": [],
    "flag_textures": {},   # ioc_code -> texture_tag
}

FLAG_SIZE = (18, 11)   # rzeczywisty rozmiar flag PNG


def load_flag_textures():
    """Ładuje wszystkie PNG z folderu ./flags jako tekstury DPG."""
    flags_dir = Path("./flags")
    if not flags_dir.exists():
        return
    with dpg.texture_registry(tag="texture_registry"):
        for png in flags_dir.glob("*.png"):
            code = png.stem.upper()   # "alb.png" -> "ALB"
            try:
                import struct, zlib
                # Wczytaj PNG przez dpg
                w, h, channels, data = dpg.load_image(str(png))
                tag = f"flag_{code}"
                dpg.add_static_texture(
                    width=w, height=h,
                    default_value=data,
                    tag=tag,
                    parent="texture_registry",
                )
                state["flag_textures"][code] = tag
            except Exception:
                pass

# ---------------------------------------------------------------------------
# CSV HELPERS
# ---------------------------------------------------------------------------

def read_csv_loose(path: Path) -> pd.DataFrame:
    encodings = ("utf-8-sig", "utf-8", "cp1250", "latin1")
    for enc in encodings:
        try:
            df = pd.read_csv(path, sep=';', engine="python", encoding=enc)
            if len(df.columns) <= 1:
                df = pd.read_csv(path, sep=None, engine="python", encoding=enc)
            if len(df.columns) > 1:
                df.columns = [str(c).replace('\ufeff', '').strip() for c in df.columns]
                return df
        except Exception:
            continue
    return pd.read_csv(path, sep=";", engine="python", encoding="utf-8-sig")


def canonicalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    seen, uniq = {}, []
    for c in out.columns:
        if c not in seen:
            seen[c] = 0; uniq.append(c)
        else:
            seen[c] += 1; uniq.append(f"{c}__{seen[c]}")
    out.columns = uniq
    return out


def format_exp(val):
    v = int(round(val))
    return f"-{v:,}".replace(",", " ") + " €" if v > 0 else "0 €"


def format_val(val):
    v = int(round(val))
    return f"{v:,}".replace(",", " ") + " €" if v != 0 else "0 €"


def format_fin(val):
    v = int(round(val))
    if v < 0:
        return f"-{abs(v):,}".replace(",", " ") + " €"
    return f"{v:,}".replace(",", " ") + " €"


def clean_money_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r'[\s\xa0€]', '', regex=True),
        errors='coerce'
    ).fillna(0)


def clean_to_num(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace(r'[^\d\.-]', '', regex=True)
    return pd.to_numeric(s, errors='coerce').fillna(0)

# ---------------------------------------------------------------------------
# TABELA — budowanie / odświeżanie
# ---------------------------------------------------------------------------

def sort_key(val):
    if pd.isna(val) or val == "":
        return (1, 0)
    if isinstance(val, (int, float)):
        return (0, val)
    s = str(val).strip()
    clean = s.replace('€','').replace('\xa0','').replace(' ','').replace(',','.')
    try:
        return (0, float(clean))
    except ValueError:
        return (1, s.lower())


def apply_filter_sort() -> pd.DataFrame:
    df = state["df"]
    if df.empty:
        return df

    # filtr
    ft = state["filter_text"].strip().lower()
    if ft:
        mask = df.apply(lambda row: row.astype(str).str.lower().str.contains(ft).any(), axis=1)
        df = df[mask]

    # sortowanie wielokolumnowe — zachowaj ORYGINALNY indeks (nie reset!)
    keys = state["sort_keys"]
    if keys:
        for col_idx, asc in reversed(keys):
            if col_idx < len(df.columns):
                col_name = df.columns[col_idx]
                df = df.iloc[
                    sorted(range(len(df)),
                           key=lambda r, cn=col_name: sort_key(df.iloc[r][cn]),
                           reverse=not asc)
                ]
    # NIE robimy reset_index — oryginalne indeksy są potrzebne w rebuild_table
    return df


def build_table_from_scratch():
    """Tworzy tabelę od zera po wczytaniu nowego pliku."""
    df = state["df"]
    if not dpg.does_item_exist("table_main"):
        return

    dpg.delete_item("table_main", children_only=True)
    state["row_tags"].clear()
    state["cell_tags"].clear()
    state["col_tags"].clear()
    state["col_names"].clear()

    if df.empty:
        return

    cols = list(df.columns)
    n_cols = len(cols)

    kraj_idx = next((i for i, c in enumerate(cols) if c.upper() == "KRAJ"), None)
    repr_idx = next((i for i, c in enumerate(cols) if c.upper() == "REPREZENTACJA"), None)

    # --- kolumny z klikalnym nagłówkiem ---
    for i, col in enumerate(cols):
        sep = " |" if i in SEP_COLS else ""
        tag = f"col_{i}"
        dpg.add_table_column(
            label="",
            tag=tag,
            parent="table_main",
            width_fixed=True,
            init_width_or_weight=col_width(col, df),
            user_data=i,
            no_header_label=True,
        )
        state["col_tags"].append(tag)
        state["col_names"].append(col + sep)

    # --- wiersz nagłówkowy z klikalnym sortowaniem ---
    with dpg.table_row(parent="table_main", tag="header_row"):
        for i, col in enumerate(cols):
            sep = " |" if i in SEP_COLS else ""
            label = col + sep
            # strzałka jeśli ta kolumna jest sortowana
            keys_dict = {k: (p, a) for p, (k, a) in enumerate(state["sort_keys"])}
            if i in keys_dict:
                pos, asc = keys_dict[i]
                arrow = "↑" if asc else "↓"
                num = f"{pos+1}" if len(state["sort_keys"]) > 1 else ""
                label = f"{col}{sep} {arrow}{num}"
            dpg.add_selectable(
                label=label,
                tag=f"hdr_{i}",
                callback=cb_header_click,
                user_data=i,
                span_columns=False,
            )

    # --- wiersze ---
    for r_idx in range(len(df)):
        row_tag = f"row_{r_idx}"

        ioc_code = ""
        if kraj_idx is not None:
            ioc_code = str(df.iat[r_idx, kraj_idx]).strip().upper()
        country_color = get_country_color(ioc_code)
        flag_tex = state["flag_textures"].get(ioc_code)

        with dpg.table_row(tag=row_tag, parent="table_main"):
            row_cells = []
            for c_idx, col in enumerate(cols):
                val = df.iat[r_idx, c_idx]
                text = "" if pd.isna(val) else str(val)
                cell_tag = f"cell_{r_idx}_{c_idx}"

                if c_idx == repr_idx:
                    # flaga PNG wyśrodkowana + nazwa
                    with dpg.group(horizontal=True, tag=cell_tag):
                        if flag_tex:
                            with dpg.group():
                                dpg.add_spacer(height=3)
                                dpg.add_image(flag_tex, width=FLAG_SIZE[0], height=FLAG_SIZE[1],
                                              tag=f"flag_img_{r_idx}")
                        dpg.add_text(text, tag=f"repr_text_{r_idx}", color=country_color)
                else:
                    dpg.add_text(text, tag=cell_tag)
                row_cells.append(cell_tag)
        state["row_tags"].append(row_tag)
        state["cell_tags"].append(row_cells)


def rebuild_table():
    """Szybkie odświeżenie: aktualizuje kolejność/widoczność wierszy bez niszczenia UI."""
    df_full = state["df"]
    if df_full.empty or not state["row_tags"]:
        dpg.set_value("status_bar", "Brak danych.")
        return

    df_sorted = apply_filter_sort()
    state["df_view"] = df_sorted

    # Zbiór indeksów (w oryginalnym df) które przeszły filtr, w kolejności po sortowaniu
    visible_original_indices = list(df_sorted.index)
    visible_set = set(visible_original_indices)

    # 1. Ukryj wszystkie wiersze
    for r_idx, row_tag in enumerate(state["row_tags"]):
        if dpg.does_item_exist(row_tag):
            dpg.hide_item(row_tag)

    # 2. Zaktualizuj tekst komórek i pokaż wiersze w nowej kolejności
    cols = list(df_full.columns)
    kraj_idx = next((i for i, c in enumerate(cols) if c.upper() == "KRAJ"), None)
    repr_idx = next((i for i, c in enumerate(cols) if c.upper() == "REPREZENTACJA"), None)

    for display_pos, orig_idx in enumerate(visible_original_indices):
        if display_pos >= len(state["row_tags"]):
            break
        row_tag = state["row_tags"][display_pos]
        if not dpg.does_item_exist(row_tag):
            continue

        # loc[orig_idx] pobiera wiersz po etykiecie indeksu (poprawne po sortowaniu)
        row_data = df_full.loc[orig_idx]

        ioc_code = ""
        if kraj_idx is not None:
            ioc_code = str(row_data.iloc[kraj_idx]).strip().upper()
        country_color = get_country_color(ioc_code)
        flag_tex = state["flag_textures"].get(ioc_code)

        for c_idx in range(len(cols)):
            cell_tag = state["cell_tags"][display_pos][c_idx]
            if not dpg.does_item_exist(cell_tag):
                continue
            val = row_data.iloc[c_idx]
            text = "" if pd.isna(val) else str(val)
            if c_idx == repr_idx:
                img_tag = f"flag_img_{display_pos}"
                txt_tag = f"repr_text_{display_pos}"
                if dpg.does_item_exist(img_tag):
                    if flag_tex:
                        dpg.configure_item(img_tag, texture_tag=flag_tex, show=True)
                    else:
                        dpg.configure_item(img_tag, show=False)
                if dpg.does_item_exist(txt_tag):
                    dpg.set_value(txt_tag, text)
                    dpg.configure_item(txt_tag, color=country_color)
            else:
                dpg.set_value(cell_tag, text)
        dpg.show_item(row_tag)

    # 3. Aktualizuj etykiety nagłówków
    keys_dict = {k: (p, a) for p, (k, a) in enumerate(state["sort_keys"])}
    if not state["df"].empty:
        cols = list(state["df"].columns)
        for i, col in enumerate(cols):
            hdr_tag = f"hdr_{i}"
            if not dpg.does_item_exist(hdr_tag):
                continue
            sep = " |" if i in SEP_COLS else ""
            label = col + sep
            if i in keys_dict:
                pos, asc = keys_dict[i]
                arrow = "↑" if asc else "↓"
                num = f"{pos+1}" if len(state["sort_keys"]) > 1 else ""
                label = f"{col}{sep} {arrow}{num}"
            dpg.configure_item(hdr_tag, label=label)

    # 4. Status bar
    total = len(df_full)
    shown = len(visible_original_indices)
    filt_txt = f" | filtr: '{state['filter_text']}'" if state["filter_text"] else ""
    sort_txt = ""
    if state["sort_col"] >= 0 and state["sort_col"] < len(df_full.columns):
        sc = df_full.columns[state["sort_col"]]
        sort_txt = f" | sort: {sc} {'↑' if state['sort_asc'] else '↓'}"
    dpg.set_value("status_bar", f"Wiersze: {shown}/{total}{filt_txt}{sort_txt}")


def col_width(col_name: str, df: pd.DataFrame) -> int:
    """Szybkie oszacowanie szerokości kolumny w pikselach."""
    max_len = len(col_name)
    sample = df[col_name].astype(str).head(200)
    if not sample.empty:
        max_len = max(max_len, sample.str.len().max())
    # ~7.5px na znak + margines, min 50, max 320
    return min(max(int(max_len * 7.5) + 20, 50), 320)


# ---------------------------------------------------------------------------
# CALLBACKI UI
# ---------------------------------------------------------------------------

def cb_header_click(sender, app_data, user_data):
    col_idx = user_data

    # Ctrl — próbujemy różne nazwy zależnie od wersji DPG
    ctrl = False
    for key_name in ("mvKey_LControl", "mvKey_Control", "mvKey_ModCtrl"):
        key = getattr(dpg, key_name, None)
        if key is not None:
            try:
                ctrl = dpg.is_key_down(key)
                break
            except Exception:
                continue
    if not ctrl:
        # fallback: GLFW Left Ctrl = 341, Right Ctrl = 345
        try:
            ctrl = dpg.is_key_down(341) or dpg.is_key_down(345)
        except Exception:
            ctrl = False

    if ctrl:
        existing = [k for k, _ in state["sort_keys"]]
        if col_idx in existing:
            state["sort_keys"] = [
                (k, not a) if k == col_idx else (k, a)
                for k, a in state["sort_keys"]
            ]
        else:
            state["sort_keys"].append((col_idx, True))
    else:
        if state["sort_keys"] == [(col_idx, True)]:
            state["sort_keys"] = [(col_idx, False)]
        elif state["sort_keys"] == [(col_idx, False)]:
            state["sort_keys"] = []
        else:
            state["sort_keys"] = [(col_idx, True)]

    state["sort_col"] = state["sort_keys"][0][0] if state["sort_keys"] else -1
    state["sort_asc"] = state["sort_keys"][0][1] if state["sort_keys"] else True

    if dpg.does_item_exist(sender):
        dpg.set_value(sender, False)

    rebuild_table()


def cb_filter(sender, app_data):
    # Filtruj dopiero po Enter (callback on_enter=True ustawiony w UI)
    state["filter_text"] = app_data
    rebuild_table()


def cb_filter_live(sender, app_data):
    # Live filtr — tylko aktualizuj stan, rebuild przy Enter
    state["filter_text"] = app_data


def cb_clear_filter(sender, app_data):
    dpg.set_value("input_filter", "")
    state["filter_text"] = ""
    rebuild_table()


def cb_browse(sender, app_data):
    dpg.show_item("file_dialog")


def cb_file_selected(sender, app_data):
    path = app_data.get("file_path_name", "")
    if path:
        dpg.set_value("input_path", path)
        state["path"] = path


def cb_load(sender, app_data):
    path = Path(dpg.get_value("input_path").strip())
    if not path.exists():
        show_error("Błąd", f"Plik nie istnieje:\n{path}")
        return
    load_file(path)


def load_file(path: Path):
    state["path"] = str(path)
    dpg.set_value("input_path", str(path))
    df = canonicalize_headers(read_csv_loose(path))
    if 'Raty' not in df.columns:
        if 'Pożyczka' in df.columns:
            idx = df.columns.get_loc('Pożyczka')
            df.insert(idx, 'Raty', 0)
        else:
            df['Raty'] = 0
    state["df"] = df
    state["sort_col"] = -1
    state["sort_asc"] = True
    state["sort_keys"] = []
    build_table_from_scratch()
    rebuild_table()


def cb_export(sender, app_data):
    df = state["df_view"]
    if df.empty:
        show_info("Eksport", "Brak danych do eksportu.")
        return
    dpg.show_item("save_dialog")


def cb_save_selected(sender, app_data):
    path = app_data.get("file_path_name", "")
    if not path:
        return
    try:
        df = state["df_view"]
        df.to_csv(path, sep=';', index=False, encoding='utf-8-sig')
        show_info("Eksport", f"Zapisano: {path}")
    except Exception as e:
        show_error("Błąd zapisu", str(e))


# ---------------------------------------------------------------------------
# OPERACJE FINANSOWE
# ---------------------------------------------------------------------------

def get_fin_path() -> Path:
    return Path(state["path"])


def save_and_reload():
    fin_path = get_fin_path()
    state["df"].to_csv(fin_path, index=False, sep=';', encoding='utf-8-sig')
    load_file(fin_path)


def cb_infrastructure(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik główny!"); return
    fin_path = get_fin_path()
    infra_path = fin_path.parent / fin_path.name.replace("Finanse", "Infrastruktura")
    expansion_path = fin_path.parent / fin_path.name.replace("Finanse", "Rozbudowa Infrastruktury")
    if not infra_path.exists():
        show_error("Błąd", f"Nie znaleziono:\n{infra_path.name}"); return
    try:
        original_columns = list(state["df"].columns)
        df_infra = read_csv_loose(infra_path)
        col_infra = next((c for c in df_infra.columns if c.upper() == "KRAJ"), None)
        col_main = next((c for c in state["df"].columns if c.upper() == "KRAJ"), None)
        mapping = {'Centrum Medyczne':'Sz','Centrum Ekonomiczne':'Ek','Centrum Inżynieryjne':'In','Centrum Edukacyjne':'Ed'}
        df_infra_mapped = df_infra.rename(columns={col_infra: col_main}).rename(columns=mapping)
        df_infra_mapped = df_infra_mapped.replace('-', '0')
        for col in mapping.values():
            if col in df_infra_mapped.columns:
                df_infra_mapped[col] = pd.to_numeric(df_infra_mapped[col], errors='coerce').fillna(0).astype(int)
        for col in mapping.values():
            if col in state["df"].columns:
                state["df"][col] = pd.to_numeric(state["df"][col], errors='coerce').fillna(0).astype(int)
        state["df"].set_index(col_main, inplace=True)
        df_infra_mapped.set_index(col_main, inplace=True)
        cols_to_update = [c for c in mapping.values() if c in state["df"].columns and c in df_infra_mapped.columns]
        if cols_to_update:
            state["df"].update(df_infra_mapped[cols_to_update])
        state["df"].reset_index(inplace=True)
        state["df"] = state["df"][original_columns]

        def clean_money(series):
            return pd.to_numeric(series.astype(str).str.replace(r'[\s\xa0€]', '', regex=True), errors='coerce').fillna(0)

        sz  = pd.to_numeric(state["df"]['Sz'], errors='coerce').fillna(0)
        ek  = pd.to_numeric(state["df"]['Ek'], errors='coerce').fillna(0)
        in_ = pd.to_numeric(state["df"]['In'], errors='coerce').fillna(0)
        ed  = pd.to_numeric(state["df"]['Ed'], errors='coerce').fillna(0)
        sp_g = clean_money(state["df"]['Sp. Główny'])
        sp_t = clean_money(state["df"]['Sp. Techniczny'])
        cost_infra = (sz*10000)+(ek*10000)+(ek*0.02*(sp_g+sp_t))+(in_*20000)+(ed*10000)

        cost_exp = pd.Series(0.0, index=state["df"].index)
        if expansion_path.exists():
            df_exp = read_csv_loose(expansion_path)
            df_exp['Cena'] = pd.to_numeric(df_exp['Cena'], errors='coerce').fillna(0)
            exp_sums = df_exp.groupby('Kraj')['Cena'].sum()
            cost_exp = state["df"][col_main].map(exp_sums).fillna(0)

        state["df"]['Infrastruktura'] = cost_infra.apply(format_exp)
        state["df"]['Roz Infr'] = cost_exp.apply(format_exp)
        save_and_reload()
        show_info("Sukces", "Zaktualizowano infrastrukturę!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_sponsorship(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik!"); return
    try:
        df = state["df"].copy()
        for col in ['M*', 'K*', 'Ek']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',','.'), errors='coerce').fillna(0)
        avg_mk = (df['M*'] + df['K*']) / 2
        ek_factor = 1 + (df['Ek'] * 0.1)
        val_g = ((avg_mk - 1) * 35000 + 300000) * ek_factor
        val_t = 20000 * avg_mk * ek_factor
        def fmt(v): return f"{int(round(v)):,}".replace(",", " ") + " €"
        state["df"]['Sp. Główny']    = val_g.apply(fmt)
        state["df"]['Sp. Techniczny'] = val_t.apply(fmt)
        save_and_reload()
        show_info("Sukces", "Przychody od sponsorów przeliczone!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_staff(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik główny!"); return
    fin_path = get_fin_path()
    sm = fin_path.parent / fin_path.name.replace("Finanse", "Sztab M")
    sw = fin_path.parent / fin_path.name.replace("Finanse", "Sztab W")
    if not sm.exists() or not sw.exists():
        show_error("Błąd", "Brak plików sztabu!"); return
    try:
        def get_costs(p):
            df_s = read_csv_loose(p)
            df_s['Money'] = df_s['Money'].astype(str).str.replace(r'[\s\xa0]','',regex=True)
            df_s['Money'] = pd.to_numeric(df_s['Money'], errors='coerce').fillna(0)
            return df_s.groupby('NAT')['Money'].sum()
        total = get_costs(sm).add(get_costs(sw), fill_value=0)
        col_main = next((c for c in state["df"].columns if c.upper()=="KRAJ"), None)
        raw_staff = state["df"][col_main].map(total).fillna(0)
        raw_ek    = pd.to_numeric(state["df"]['Ek'].astype(str).str.replace(',','.'), errors='coerce').fillna(0)
        state["df"]['Sztab']    = raw_staff.apply(format_exp)
        state["df"]['Sztab Ek'] = (raw_staff * (raw_ek * 0.1)).apply(format_val)
        save_and_reload()
        show_info("Sukces", "Zaktualizowano koszty sztabu!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_hills(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik główny!"); return
    fin_path = get_fin_path()
    hills_path = fin_path.parent / fin_path.name.replace("Finanse","Utrzymanie Skoczni")
    if not hills_path.exists():
        show_error("Błąd", f"Nie znaleziono:\n{hills_path.name}"); return
    season = fin_path.stem.split()[-1]
    exp_candidates = [
        fin_path.parent / fin_path.name.replace("Finanse","Rozbudowa"),
        fin_path.parent / f"Koszty_rozbudowy_skoczni_{season}.csv",
        fin_path.parent / f"Rozbudowa Skoczni {season}.csv",
    ]
    exp_path = next((p for p in exp_candidates if p.exists()), exp_candidates[0])
    try:
        df_h = read_csv_loose(hills_path)
        df_h['Suma'] = clean_money_series(df_h['Suma'])
        hills_map = df_h.set_index('Kraj')['Suma']
        exp_sums = pd.Series(dtype=float)
        if exp_path.exists():
            df_exp = read_csv_loose(exp_path)
            ec = next((c for c in df_exp.columns if c in ('Cena','Suma')), None)
            if ec:
                df_exp[ec] = clean_money_series(df_exp[ec])
                exp_sums = df_exp.groupby('Kraj')[ec].sum()
        col_main = next((c for c in state["df"].columns if c.upper()=="KRAJ"), None)
        raw_hills = state["df"][col_main].map(hills_map).fillna(0)
        raw_in    = pd.to_numeric(state["df"]['In'].astype(str).str.replace(',','.'), errors='coerce').fillna(0)
        raw_exp   = state["df"][col_main].map(exp_sums).fillna(0)
        state["df"]['Skocznie']    = raw_hills.apply(format_exp)
        state["df"]['Skocznie In'] = (raw_hills * (raw_in * 0.04)).apply(format_val)
        state["df"]['Roz Skoczni'] = raw_exp.apply(format_exp)
        save_and_reload()
        show_info("Sukces", "Zaktualizowano Skocznie!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_camps(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik główny!"); return
    fin_path = get_fin_path()
    camps_path = fin_path.parent / fin_path.name.replace("Finanse","Koszty Obozu")
    if not camps_path.exists():
        show_error("Błąd", f"Nie znaleziono:\n{camps_path.name}"); return
    try:
        df_c = read_csv_loose(camps_path)
        cc = next((c for c in df_c.columns if c.upper()=="KRAJ"), None)
        ck = next((c for c in df_c.columns if c.upper()=="KOSZT"), None)
        if not cc or not ck:
            show_error("Błąd", "Brak kolumn Kraj/Koszt w pliku obozów"); return
        df_c[ck] = clean_money_series(df_c[ck])
        camps_map = df_c.groupby(cc)[ck].sum()
        col_main = next((c for c in state["df"].columns if c.upper()=="KRAJ"), None)
        state["df"]['Obozy Sz.']  = state["df"][col_main].map(camps_map).fillna(0).apply(format_exp)
        state["df"]['Obozy Lecz.'] = "0 €"
        save_and_reload()
        show_info("Sukces", "Zaktualizowano obozy!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_juniors(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik główny!"); return
    fin_path = get_fin_path()
    jp = fin_path.parent / fin_path.name.replace("Finanse","Koszty Juniorów")
    if not jp.exists():
        show_error("Błąd", f"Nie znaleziono:\n{jp.name}"); return
    try:
        df_j = read_csv_loose(jp)
        if 'Suma Kosztów' not in df_j.columns or 'Kraj' not in df_j.columns:
            show_error("Błąd", "Brak kolumn Kraj/Suma Kosztów"); return
        df_j['Suma Kosztów'] = clean_money_series(df_j['Suma Kosztów'])
        jmap = df_j.groupby('Kraj')['Suma Kosztów'].sum()
        col_main = next((c for c in state["df"].columns if c.upper()=="KRAJ"), None)
        state["df"]['Juniorzy'] = state["df"][col_main].map(jmap).fillna(0).apply(format_exp)
        save_and_reload()
        show_info("Sukces", "Zaktualizowano juniorów!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_competitions(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik!"); return
    fin_path = get_fin_path()
    zp = fin_path.parent / fin_path.name.replace("Finanse","Zysk Konkursy")
    if not zp.exists():
        show_error("Błąd", f"Nie znaleziono:\n{zp.name}"); return
    try:
        df_z = read_csv_loose(zp)
        cc = next((c for c in df_z.columns if c.upper() in ["KRAJ","NAT"]), None)
        ck = next((c for c in df_z.columns if "ZYSK FINALNY" in c.upper()), None)
        if not cc or not ck:
            show_error("Błąd", "Brak kolumn NAT/Kraj lub Zysk Finalny"); return
        df_z[ck] = clean_money_series(df_z[ck])
        zmap = df_z.groupby(cc)[ck].sum()
        col_main = next((c for c in state["df"].columns if c.upper()=="KRAJ"), None)
        state["df"]['Konkursy'] = state["df"][col_main].map(zmap).fillna(0).apply(
            lambda v: f"{int(round(v)):,}".replace(",", " ") + " €")
        save_and_reload()
        show_info("Sukces", "Zaktualizowano konkursy!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_prizes(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik!"); return
    fin_path = get_fin_path()
    pp = fin_path.parent / fin_path.name.replace("Finanse","Nagrody")
    if not pp.exists():
        show_error("Błąd", f"Nie znaleziono:\n{pp.name}"); return
    try:
        df_p = read_csv_loose(pp)
        if 'NAT' not in df_p.columns or 'SUMA' not in df_p.columns:
            show_error("Błąd", "Brak kolumn NAT lub SUMA w pliku nagród"); return
        df_p['SUMA'] = pd.to_numeric(
            df_p['SUMA'].astype(str).str.replace(r'[^\d.]','',regex=True), errors='coerce').fillna(0)
        pdict = df_p.set_index('NAT')['SUMA'].to_dict()
        if 'KRAJ' not in state["df"].columns:
            show_error("Błąd", "Brak kolumny KRAJ w arkuszu głównym"); return
        state["df"]['Nagrody'] = state["df"]['KRAJ'].map(pdict).fillna(0).apply(
            lambda v: f"{int(float(v)):,}".replace(",", " ") + " €" if int(float(v)) > 0 else "0 €")
        save_and_reload()
        show_info("Sukces", "Nagrody zaktualizowane!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_budget(sender, app_data):
    if state["df"].empty:
        show_error("Błąd", "Najpierw wczytaj plik!"); return
    try:
        fin_path = get_fin_path()
        match = re.search(r'S(\d+)', fin_path.name)
        s_val = f"S{match.group(1)}" if match else "S51"
        base_dir = Path(f"./{s_val}")
        file_m = base_dir / f"Ranking FIS M {s_val}.csv"
        file_w = base_dir / f"Ranking FIS W {s_val}.csv"

        def get_stars(fp):
            if not fp.exists(): return {}
            rdf = pd.read_csv(fp, sep=';', encoding='utf-8-sig')
            rdf.columns = [str(c).strip() for c in rdf.columns]
            if 'NAT' in rdf.columns and '*' in rdf.columns:
                return dict(zip(rdf['NAT'], rdf['*']))
            return {}

        stars_m = get_stars(file_m)
        stars_w = get_stars(file_w)
        if 'KRAJ' in state["df"].columns:
            state["df"]['M*.1'] = state["df"]['KRAJ'].map(stars_m).fillna(0).astype(int)
            state["df"]['K*.1'] = state["df"]['KRAJ'].map(stars_w).fillna(0).astype(int)

        cols_to_sum = [
            'BUDŻET STARTOWY','Pożyczka','Sp. Główny','Sp. Techniczny',
            'Konkursy','Nagrody','Sztab','Sztab Ek','Skocznie',
            'Skocznie In','Roz Skoczni','Infrastruktura','Roz Infr',
            'Obozy Sz.','Obozy Lecz.','Juniorzy'
        ]
        total = pd.Series(0.0, index=state["df"].index)
        for col in cols_to_sum:
            if col in state["df"].columns:
                total += clean_to_num(state["df"][col])

        budzet_koncowy = total
        surplus = budzet_koncowy.apply(lambda x: x * 0.25 if x > 0 else x)
        stars_avg = (state["df"]['M*.1'] + state["df"]['K*.1']) / 2
        next_start = surplus + 750000 + (stars_avg * 200000)

        state["df"]['BUDŻET KOŃCOWY'] = budzet_koncowy.apply(format_fin)
        state["df"]['Nadwyżka']       = surplus.apply(format_fin)
        state["df"]['Budżet startowy'] = next_start.apply(format_fin)
        save_and_reload()
        show_info("Sukces", f"Zaktualizowano budżet dla sezonu {s_val}!")
    except Exception as e:
        show_error("Błąd", str(e))


def cb_new_season(sender, app_data):
    dpg.show_item("popup_new_season")


def cb_new_season_confirm(sender, app_data):
    nowy_sezon = dpg.get_value("input_new_season").strip()
    dpg.hide_item("popup_new_season")
    if not nowy_sezon:
        return
    try:
        liczby = re.findall(r'\d+', nowy_sezon)
        if not liczby:
            show_error("Błąd", "Nazwa musi zawierać numer (np. S51)"); return
        numer_nowego = int(liczby[0])
        numer_starego = numer_nowego - 1
        stary_sezon = f"S{numer_starego}"
        sciezka_stara = os.path.join(stary_sezon, f"Finanse {stary_sezon}.csv")
        if not os.path.exists(sciezka_stara) and numer_starego == 38:
            sciezka_stara = "Finanse S51.csv"
        if not os.path.exists(sciezka_stara):
            show_error("Błąd", f"Nie znaleziono: {sciezka_stara}"); return

        if not os.path.exists(nowy_sezon):
            os.makedirs(nowy_sezon)
        sciezka_nowa = os.path.join(nowy_sezon, f"Finanse {nowy_sezon}.csv")

        df = pd.read_csv(sciezka_stara, sep=';')

        def to_num(val):
            if pd.isna(val) or val == "": return 0.0
            if isinstance(val, str):
                return float(val.replace('€','').replace('\xa0','').replace(' ','').replace(',','.'))
            return float(val)

        df['M*'] = df['M*.1']
        df['K*'] = df['K*.1']
        if 'Budżet startowy' in df.columns:
            df['BUDŻET STARTOWY'] = df['Budżet startowy']
        else:
            df['BUDŻET STARTOWY'] = df['BUDŻET KOŃCOWY']

        nowe_pozyczki, raty_akt = [], []
        for _, row in df.iterrows():
            bs = to_num(row['BUDŻET STARTOWY'])
            raty = int(row['Raty']) if 'Raty' in df.columns else 0
            if bs < 0 and raty == 0:
                nowe_pozyczki.append("1 200 000 €"); raty_akt.append(4)
            elif raty > 0:
                nowe_pozyczki.append("-300 000 €"); raty_akt.append(raty - 1)
            else:
                nowe_pozyczki.append("0 €"); raty_akt.append(0)

        df['Pożyczka'] = nowe_pozyczki
        df['Raty']     = raty_akt

        for col in ['Konkursy','Nagrody','Roz Infr','Obozy Sz.','Juniorzy','Obozy Lecz.','Nadwyżka']:
            if col in df.columns: df[col] = "0 €"
        for col in ['M*.1','K*.1']:
            if col in df.columns: df[col] = 0

        df.to_csv(sciezka_nowa, sep=';', index=False)
        show_info("Sukces", f"Zapisano: {sciezka_nowa}")
    except Exception as e:
        show_error("Błąd", str(e))


# ---------------------------------------------------------------------------
# DIALOGI
# ---------------------------------------------------------------------------

def show_error(title: str, msg: str):
    dpg.set_value("popup_msg_text", msg)
    dpg.configure_item("popup_msg", label=title)
    dpg.show_item("popup_msg")


def show_info(title: str, msg: str):
    dpg.set_value("popup_msg_text", msg)
    dpg.configure_item("popup_msg", label=title)
    dpg.show_item("popup_msg")


# ---------------------------------------------------------------------------
# BUDOWANIE UI
# ---------------------------------------------------------------------------

def build_ui():
    dpg.create_context()
    dpg.create_viewport(title="Finanse — Panel Sterowania", width=1400, height=900)
    dpg.setup_dearpygui()

    # --- Czcionka z polskimi znakami, €, emoji flag ---
    font_candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
    ]
    # Czcionka do emoji flag (Segoe UI Emoji lub podobna)
    emoji_candidates = [
        "C:/Windows/Fonts/seguiemj.ttf",  # Segoe UI Emoji
        "C:/Windows/Fonts/seguisym.ttf",  # Segoe UI Symbol
    ]
    with dpg.font_registry():
        for path in font_candidates:
            if os.path.exists(path):
                dpg.add_font(path, 17, tag="font_pl")
                dpg.add_font_range(0x0100, 0x017F, parent="font_pl")
                dpg.add_font_range(0x20A0, 0x20CF, parent="font_pl")
                break

    # --- Ładowanie flag PNG z folderu ./flags ---
    load_flag_textures()

    # --- File dialog (otwieranie) ---
    with dpg.file_dialog(
        directory_selector=False, show=False,
        callback=cb_file_selected, tag="file_dialog",
        width=700, height=450
    ):
        dpg.add_file_extension(".csv", color=(0, 200, 100, 255))
        dpg.add_file_extension(".*")

    # --- File dialog (zapis) ---
    with dpg.file_dialog(
        directory_selector=False, show=False,
        callback=cb_save_selected, tag="save_dialog",
        width=700, height=450
    ):
        dpg.add_file_extension(".csv")

    # --- Popup: wiadomości ---
    with dpg.window(label="Info", tag="popup_msg", show=False, modal=True,
                    width=420, height=160, pos=[490, 370], no_resize=True):
        dpg.add_text("", tag="popup_msg_text", wrap=390)
        dpg.add_spacer(height=8)
        dpg.add_button(label="OK", width=80, callback=lambda: dpg.hide_item("popup_msg"))

    # --- Popup: nowy sezon ---
    with dpg.window(label="Nowy Sezon", tag="popup_new_season", show=False, modal=True,
                    width=340, height=130, pos=[530, 385], no_resize=True):
        dpg.add_text("Podaj nazwę nowego sezonu (np. S51):")
        dpg.add_input_text(tag="input_new_season", default_value="", width=200)
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_button(label="OK",     width=80, callback=cb_new_season_confirm)
            dpg.add_button(label="Anuluj", width=80, callback=lambda: dpg.hide_item("popup_new_season"))

    # --- Główne okno ---
    with dpg.window(tag="main_window", label="", no_title_bar=True,
                    no_resize=True, no_move=True, no_close=True):

        # --- pasek pliku ---
        with dpg.group(horizontal=True):
            dpg.add_text("Plik:")
            init_path = ""
            for c in DEFAULT_CANDIDATES:
                if c.exists(): init_path = str(c); break
            dpg.add_input_text(tag="input_path", default_value=init_path, width=-140)
            dpg.add_button(label="…",       width=30,  callback=cb_browse)
            dpg.add_button(label="Wczytaj", width=100, callback=cb_load)

        dpg.add_spacer(height=4)

        # --- filtr ---
        with dpg.group(horizontal=True):
            dpg.add_text("Filtr:")
            dpg.add_input_text(tag="input_filter", hint="szukaj... (Enter aby filtrować)", width=-90,
                               callback=cb_filter, on_enter=True)
            dpg.add_button(label="Wyczyść", width=80, callback=cb_clear_filter)

        dpg.add_spacer(height=4)

        # --- przyciski operacji (2 × 5) ---
        btn_defs = [
            ("Infrastruktura",  cb_infrastructure),
            ("Sponsorzy",       cb_sponsorship),
            ("Sztab",           cb_staff),
            ("Skocznie",        cb_hills),
            ("Obozy",           cb_camps),
            ("Juniorzy",        cb_juniors),
            ("Konkursy",        cb_competitions),
            ("Nagrody",         cb_prizes),
            ("Budżet i Nadwyżka", cb_budget),
            ("Nowy Sezon",      cb_new_season),
        ]
        for row_idx in range(2):
            with dpg.group(horizontal=True):
                for col_idx in range(5):
                    btn_i = row_idx * 5 + col_idx
                    label, cb = btn_defs[btn_i]
                    dpg.add_button(label=label, width=200, height=28, callback=cb)
            dpg.add_spacer(height=2)

        dpg.add_spacer(height=4)

        # przycisk eksportu
        dpg.add_button(label="Eksportuj widok do CSV", callback=cb_export, height=26)

        dpg.add_spacer(height=4)

        # --- tabela ---
        with dpg.table(
            tag="table_main",
            header_row=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            borders_innerH=False,
            row_background=True,
            scrollX=True,
            scrollY=True,
            freeze_columns=2,
            resizable=True,
            policy=dpg.mvTable_SizingFixedFit,
            height=-40,
        ):
            pass  # kolumny i wiersze dodawane dynamicznie

        dpg.add_spacer(height=4)
        dpg.add_text("Wiersze: 0/0", tag="status_bar")

    # ustaw rozmiar głównego okna = rozmiar viewportu
    dpg.set_primary_window("main_window", True)

    # zastosuj czcionkę globalnie
    if dpg.does_item_exist("font_pl"):
        dpg.bind_font("font_pl")

    # załaduj plik jeśli istnieje domyślny
    if init_path:
        load_file(Path(init_path))


def cb_table_sort(sender, sort_specs):
    """Callback sortowania — DPG przekazuje listę (col_id, direction)."""
    if sort_specs is None or len(sort_specs) == 0:
        state["sort_keys"] = []
        state["sort_col"] = -1
        rebuild_table()
        return

    new_keys = []
    for col_id, direction in sort_specs:
        try:
            idx = dpg.get_item_user_data(col_id)
            if idx is None:
                idx = 0
        except Exception:
            idx = 0
        new_keys.append((idx, direction > 0))

    state["sort_keys"] = new_keys
    # aktualizuj sort_col/sort_asc dla wstecznej kompatybilności
    if new_keys:
        state["sort_col"] = new_keys[0][0]
        state["sort_asc"] = new_keys[0][1]
    else:
        state["sort_col"] = -1
    rebuild_table()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    build_ui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
