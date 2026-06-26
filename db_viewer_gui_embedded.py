#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db_viewer_gui_embedded.py
Moduł do przeglądania bazy danych manager_skokow.db
z obsługą filtrowania, sortowania i widoku aktualnych rekordów.
"""

import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ── Domyślna ścieżka DB ──────────────────────────────────────────────────────
_DEFAULT_DB = Path(__file__).parent / "manager_skokow.db"

# ── Które tabele mają tryb "Aktualne rekordy" ────────────────────────────────
# Wartość to nazwa kolumny z płcią w zbiorze wyników (0-based index)
RECORDS_TABLES = {"Rekordy skoczni", "Rekordy świata", "Rekordy krajowe"}

# ── Konfiguracja tabel ───────────────────────────────────────────────────────
TABLES_CONFIG = {
    "Zawodnicy": {
        "sql": """
            SELECT z.id, z.zawodnik, z.kraj, z.płeć,
                   COALESCE(sk.rekord_odleglosc, '') AS rekord_odl,
                   COALESCE(sk.rekord_skocznia, '') AS rekord_skocznia,
                   COALESCE(sk.rekord_sezon, '') AS rekord_sezon,
                   COALESCE(sk.konkursy_lacznie, 0) AS konkursy,
                   COALESCE(sk.punkty_lacznie, 0) AS punkty
            FROM zawodnicy z
            LEFT JOIN statystyki_kariery sk ON sk.zawodnik_id = z.id
        """,
        "cols": ["ID", "Zawodnik", "Kraj", "Płeć", "Rekord [m]", "Skocznia rekordu",
                 "Sezon rekordu", "Konkursy", "Punkty"],
        "search_cols": [1, 2, 3],
        "numeric_cols": [0, 4, 7, 8],
    },
    "Skocznie": {
        "sql": "SELECT id, kraj, miasto, skocznia, k, hs FROM skocznie",
        "cols": ["ID", "Kraj", "Miasto", "Skocznia", "K [m]", "HS [m]"],
        "search_cols": [1, 2, 3],
        "numeric_cols": [0, 4, 5],
    },
    # ── Historia wszystkich pobić ──
    "Rekordy skoczni": {
        # Historia: LEFT JOIN – skocznie bez rekordów też się pojawiają (NULL w kolumnach rekordu)
        "sql": """
            SELECT s.kraj, s.miasto, s.skocznia, s.hs,
                   r.rekord_odl, r.zawodnik, r.kraj_zawodnika, r.sezon, r.plec, r.data_wpisu
            FROM skocznie s
            LEFT JOIN nowe_rekordy_skoczni r ON r.id_skoczni = s.id
            ORDER BY s.kraj, s.skocznia, r.plec, r.rekord_odl DESC
        """,
        "cols": ["Kraj skoczni", "Miasto", "Skocznia", "HS [m]", "Rekord [m]",
                 "Zawodnik", "Kraj zawodnika", "Sezon", "Płeć", "Data wpisu"],
        "search_cols": [0, 1, 2, 5, 6],
        "numeric_cols": [3, 4],
        # Widok aktualnych: LEFT JOIN żeby pokazać też skocznie bez rekordu M/W
        "sql_current_M": """
            SELECT s.kraj, s.miasto, s.skocznia, s.hs,
                   r.rekord_odl, r.zawodnik, r.kraj_zawodnika, r.sezon, r.plec, r.data_wpisu
            FROM skocznie s
            LEFT JOIN nowe_rekordy_skoczni r
                ON r.id_skoczni = s.id
               AND r.plec = 'M'
               AND r.rekord_odl = (
                   SELECT MAX(r2.rekord_odl) FROM nowe_rekordy_skoczni r2
                   WHERE r2.id_skoczni = s.id AND r2.plec = 'M'
               )
            ORDER BY s.kraj, s.skocznia
        """,
        "sql_current_W": """
            SELECT s.kraj, s.miasto, s.skocznia, s.hs,
                   r.rekord_odl, r.zawodnik, r.kraj_zawodnika, r.sezon, r.plec, r.data_wpisu
            FROM skocznie s
            LEFT JOIN nowe_rekordy_skoczni r
                ON r.id_skoczni = s.id
               AND r.plec = 'W'
               AND r.rekord_odl = (
                   SELECT MAX(r2.rekord_odl) FROM nowe_rekordy_skoczni r2
                   WHERE r2.id_skoczni = s.id AND r2.plec = 'W'
               )
            ORDER BY s.kraj, s.skocznia
        """,
        "cols_current": ["Kraj skoczni", "Miasto", "Skocznia", "HS [m]", "Rekord [m]",
                         "Zawodnik", "Kraj zawodnika", "Sezon", "Płeć", "Data wpisu"],
        "search_cols_current": [0, 1, 2, 5, 6],
        "numeric_cols_current": [3, 4],
    },
    "Rekordy świata": {
        "sql": """
            SELECT rekord_odl, zawodnik, kraj_zawodnika, skocznia, sezon, plec, data_wpisu
            FROM nowe_rekordy_swiata
            ORDER BY plec, rekord_odl DESC
        """,
        "cols": ["Rekord [m]", "Zawodnik", "Kraj", "Skocznia", "Sezon", "Płeć", "Data wpisu"],
        "search_cols": [1, 2, 3],
        "numeric_cols": [0],
        # Widok aktualnych: tabela rekordy_swiata zawiera już aktualny snapshot (1 rekord M, 1 W)
        "sql_current_M": """
            SELECT rekord_odl, zawodnik, kraj_zawodnika, skocznia, sezon, plec
            FROM rekordy_swiata
            WHERE plec = 'M'
        """,
        "sql_current_W": """
            SELECT rekord_odl, zawodnik, kraj_zawodnika, skocznia, sezon, plec
            FROM rekordy_swiata
            WHERE plec = 'W'
        """,
        "cols_current": ["Rekord [m]", "Zawodnik", "Kraj", "Skocznia", "Sezon", "Płeć"],
        "search_cols_current": [1, 2, 3],
        "numeric_cols_current": [0],
    },
    "Rekordy krajowe": {
        "sql": """
            SELECT nat, reprezentacja, rekord_odl, zawodnik, skocznia, sezon, plec, data_wpisu
            FROM nowe_rekordy_krajowe
            ORDER BY nat, plec, rekord_odl DESC
        """,
        "cols": ["Kod", "Reprezentacja", "Rekord [m]", "Zawodnik",
                 "Skocznia", "Sezon", "Płeć", "Data wpisu"],
        "search_cols": [0, 1, 3, 4],
        "numeric_cols": [2],
        # Widok aktualnych: tabela rekordy_krajowe ma M i W w osobnych kolumnach
        # Rozwijamy do osobnych wierszy per plec
        "sql_current_M": """
            SELECT nat, reprezentacja, rekord_m AS rekord_odl, zawodnik_m AS zawodnik,
                   skocznia_m AS skocznia, sezon_m AS sezon, 'M' AS plec
            FROM rekordy_krajowe
            WHERE rekord_m IS NOT NULL
            ORDER BY nat
        """,
        "sql_current_W": """
            SELECT nat, reprezentacja, rekord_w AS rekord_odl, zawodnik_w AS zawodnik,
                   skocznia_w AS skocznia, sezon_w AS sezon, 'W' AS plec
            FROM rekordy_krajowe
            WHERE rekord_w IS NOT NULL
            ORDER BY nat
        """,
        "cols_current": ["Kod", "Reprezentacja", "Rekord [m]", "Zawodnik",
                         "Skocznia", "Sezon", "Płeć"],
        "search_cols_current": [0, 1, 3, 4],
        "numeric_cols_current": [2],
    },
    "Statystyki kariery": {
        "sql": """
            SELECT z.zawodnik, z.kraj, z.płeć,
                   sk.rekord_odleglosc,
                   sk.konkursy_lacznie, sk.punkty_lacznie,
                   sk.konkursy_wc, sk.punkty_wc,
                   sk.konkursy_coc, sk.punkty_coc,
                   sk.konkursy_fc, sk.punkty_fc,
                   sk.konkursy_gp, sk.punkty_gp,
                   sk.konkursy_jun, sk.punkty_jun,
                   sk.miejsce_wc, sk.miejsce_coc, sk.miejsce_fc,
                   sk.miejsce_gp, sk.miejsce_jun
            FROM statystyki_kariery sk
            JOIN zawodnicy z ON z.id = sk.zawodnik_id
        """,
        "cols": [
            "Zawodnik", "Kraj", "Płeć", "Rekord [m]",
            "Kk łącznie", "Pkt łącznie",
            "Kk WC", "Pkt WC",
            "Kk COC", "Pkt COC",
            "Kk FC", "Pkt FC",
            "Kk GP", "Pkt GP",
            "Kk JUN", "Pkt JUN",
            "Msc WC", "Msc COC", "Msc FC", "Msc GP", "Msc JUN",
        ],
        "search_cols": [0, 1, 2],
        "numeric_cols": [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
    },
}


def _try_num(v):
    """Klucz sortowania: zawsze zwraca tuple (typ, wartość) żeby uniknąć
    porównania float vs str gdy kolumna ma mieszane lub NULL-owe wartości.
    Liczby → (0, float), teksty → (1, str), None/puste → (2, '')
    """
    if v is None or str(v).strip() == '':
        return (2, '')
    try:
        return (0, float(v))
    except (ValueError, TypeError):
        return (1, str(v).lower())


# ── Główny widget ─────────────────────────────────────────────────────────────

class DBViewerFrame(ttk.Frame):
    def __init__(self, parent, db_path=None):
        super().__init__(parent)
        self._db_path = str(db_path or _DEFAULT_DB)
        self._conn = None
        self._all_rows = []
        self._sort_col = None
        self._sort_asc = True
        self._cfg = None
        # Tryb widoku rekordów: None = historia, 'M' lub 'W' = aktualne
        self._records_mode = None
        # Widgety przycisków trybu – przechowujemy do ukrycia/pokazania
        self._records_bar = None

        self._build_toolbar()
        self._build_records_bar()   # pasek z przyciskami M/W/Historia
        self._build_filter_bar()
        self._build_tree()
        self._build_statusbar()

        self._open_db(self._db_path)

    # ── UI builder ───────────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(4, 4, 4, 2))
        bar.pack(fill=tk.X)

        ttk.Label(bar, text="Baza:").pack(side=tk.LEFT)
        self._db_var = tk.StringVar(value=self._db_path)
        ttk.Entry(bar, textvariable=self._db_var, width=48).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Otwórz…", command=self._pick_db).pack(side=tk.LEFT)
        ttk.Button(bar, text="Odśwież", command=self._reload).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=8, fill=tk.Y)

        ttk.Label(bar, text="Tabela:").pack(side=tk.LEFT)
        self._table_var = tk.StringVar()
        cb = ttk.Combobox(bar, textvariable=self._table_var,
                          values=list(TABLES_CONFIG.keys()), state="readonly", width=22)
        cb.pack(side=tk.LEFT, padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._on_table_selected())
        self._table_var.set(list(TABLES_CONFIG.keys())[0])

        ttk.Button(bar, text="Eksportuj CSV…", command=self._export_csv).pack(side=tk.RIGHT)

    def _build_records_bar(self):
        """Pasek z przyciskami trybu rekordów – widoczny tylko dla tabel rekordowych."""
        self._records_bar = ttk.Frame(self, padding=(4, 0, 4, 2))
        # Nie pakujemy od razu – zarządza tym _toggle_records_bar()

        # Etykieta opisu
        ttk.Label(self._records_bar, text="Widok:").pack(side=tk.LEFT)

        self._mode_var = tk.StringVar(value="historia")

        style = ttk.Style()
        # Aktywny przycisk będzie wyróżniony przez zmianę tekstu – używamy Radiobutton
        self._btn_hist = ttk.Radiobutton(
            self._records_bar, text="📜  Historia (wszystkie rekordy)",
            variable=self._mode_var, value="historia",
            command=self._on_mode_change
        )
        self._btn_hist.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Separator(self._records_bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, padx=10, fill=tk.Y)

        ttk.Label(self._records_bar, text="Aktualne rekordy:").pack(side=tk.LEFT)

        self._btn_M = ttk.Radiobutton(
            self._records_bar, text="♂  Mężczyźni (M)",
            variable=self._mode_var, value="M",
            command=self._on_mode_change
        )
        self._btn_M.pack(side=tk.LEFT, padx=(6, 0))

        self._btn_W = ttk.Radiobutton(
            self._records_bar, text="♀  Kobiety (W)",
            variable=self._mode_var, value="W",
            command=self._on_mode_change
        )
        self._btn_W.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Separator(self._records_bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, padx=10, fill=tk.Y)

        self._btn_both = ttk.Radiobutton(
            self._records_bar, text="⚥  Oboje",
            variable=self._mode_var, value="MiW",
            command=self._on_mode_change
        )
        self._btn_both.pack(side=tk.LEFT)

    def _build_filter_bar(self):
        bar = ttk.Frame(self, padding=(4, 2, 4, 4))
        bar.pack(fill=tk.X)

        ttk.Label(bar, text="Szukaj:").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filters())
        ttk.Entry(bar, textvariable=self._search_var, width=30).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="✕", width=2,
                   command=lambda: self._search_var.set("")).pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)

        self._filter_labels = []
        self._filter_vars = []
        self._filter_col_indices = []
        self._filter_entries = []
        self._filter_frame = bar

    def _build_tree(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 2))

        self._tree = ttk.Treeview(frame, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self._tree.tag_configure("odd",  background="#f5f8ff")
        self._tree.tag_configure("even", background="#ffffff")
        # Kolory wierszy M/W w trybie aktualnych rekordów
        self._tree.tag_configure("row_M", background="#ddeeff")   # niebieskawa
        self._tree.tag_configure("row_W", background="#ffeedd")   # różowawa

    def _build_statusbar(self):
        self._status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._status_var, anchor=tk.W,
                  foreground="gray").pack(fill=tk.X, padx=6, pady=(0, 4))

    # ── Pasek trybu – pokaż / ukryj ──────────────────────────────────────────

    def _toggle_records_bar(self, show: bool):
        if show:
            self._records_bar.pack(fill=tk.X, after=self.winfo_children()[0])
        else:
            self._records_bar.pack_forget()

    # ── Zdarzenia UI ──────────────────────────────────────────────────────────

    def _on_table_selected(self):
        name = self._table_var.get()
        is_records = name in RECORDS_TABLES
        self._toggle_records_bar(is_records)
        if not is_records:
            self._mode_var.set("historia")
        self._load_table()

    def _on_mode_change(self):
        self._load_table()

    # ── DB ────────────────────────────────────────────────────────────────────

    def _open_db(self, path: str):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        try:
            self._conn = sqlite3.connect(path)
            self._db_path = path
            self._db_var.set(path)
            self._on_table_selected()
        except Exception as exc:
            messagebox.showerror("Błąd otwarcia bazy", str(exc), parent=self)

    def _pick_db(self):
        p = filedialog.askopenfilename(
            title="Wybierz bazę danych",
            filetypes=[("SQLite", "*.db *.sqlite *.sqlite3"), ("Wszystkie", "*.*")]
        )
        if p:
            self._open_db(p)

    def _reload(self):
        self._load_table()

    # ── Wyznaczanie SQL i metadanych dla bieżącego widoku ────────────────────

    def _resolve_view(self):
        """
        Zwraca (sql_or_list_of_sqls, cols, search_cols, numeric_cols)
        w zależności od aktualnej tabeli i trybu M/W/historia.
        sql_or_list_of_sqls może być:
          - str  → pojedyncze zapytanie
          - list → lista zapytań (UNION), wyniki zostaną scalone
        """
        name = self._table_var.get()
        cfg = TABLES_CONFIG.get(name)
        if not cfg:
            return None, [], [], []

        mode = self._mode_var.get()

        if name not in RECORDS_TABLES or mode == "historia":
            return cfg["sql"], cfg["cols"], cfg["search_cols"], cfg.get("numeric_cols", [])

        # Tryb aktualnych rekordów
        cols    = cfg["cols_current"]
        s_cols  = cfg["search_cols_current"]
        n_cols  = cfg.get("numeric_cols_current", [])

        if mode == "M":
            return cfg["sql_current_M"], cols, s_cols, n_cols
        elif mode == "W":
            return cfg["sql_current_W"], cols, s_cols, n_cols
        else:  # MiW – oboje
            return [cfg["sql_current_M"], cfg["sql_current_W"]], cols, s_cols, n_cols

    # ── Ładowanie tabeli ──────────────────────────────────────────────────────

    def _load_table(self):
        name = self._table_var.get()
        sql, cols, search_cols, numeric_cols = self._resolve_view()
        if not sql or not self._conn:
            return

        self._cfg = {
            "cols": cols,
            "search_cols": search_cols,
            "numeric_cols": numeric_cols,
        }

        try:
            cur = self._conn.cursor()
            if isinstance(sql, list):
                rows = []
                for q in sql:
                    cur.execute(q)
                    rows.extend(cur.fetchall())
                self._all_rows = rows
            else:
                cur.execute(sql)
                self._all_rows = cur.fetchall()
        except Exception as exc:
            messagebox.showerror("Błąd zapytania", str(exc), parent=self)
            return

        self._sort_col = None
        self._sort_asc = True
        self._search_var.set("")
        self._setup_columns()
        self._refresh_filter_entries()
        self._apply_filters()

    def _setup_columns(self):
        cols = self._cfg["cols"]
        self._tree["columns"] = cols
        for i, c in enumerate(cols):
            anchor = tk.E if i in self._cfg.get("numeric_cols", []) else tk.W
            sample_vals = [str(r[i]) for r in self._all_rows[:50] if i < len(r) and r[i] is not None]
            max_len = max((len(v) for v in sample_vals), default=4)
            width = max(50, min(260, max(len(c) * 9, max_len * 7 + 10)))
            self._tree.heading(c, text=c, command=lambda _c=i: self._sort_by(_c))
            self._tree.column(c, width=width, anchor=anchor, stretch=False)

    def _refresh_filter_entries(self):
        for lbl in self._filter_labels:
            lbl.destroy()
        for entry_w in self._filter_entries:
            entry_w.destroy()
        self._filter_labels.clear()
        self._filter_vars.clear()
        self._filter_col_indices.clear()
        self._filter_entries.clear()

        if not self._cfg:
            return

        cols = self._cfg["cols"]
        for col_idx in self._cfg.get("search_cols", [])[:4]:
            col_name = cols[col_idx]
            lbl = ttk.Label(self._filter_frame, text=f"{col_name}:")
            lbl.pack(side=tk.LEFT, padx=(6, 0))
            var = tk.StringVar()
            var.trace_add("write", lambda *_: self._apply_filters())
            entry = ttk.Entry(self._filter_frame, textvariable=var, width=14)
            entry.pack(side=tk.LEFT, padx=(2, 0))
            self._filter_labels.append(lbl)
            self._filter_vars.append(var)
            self._filter_col_indices.append(col_idx)
            self._filter_entries.append(entry)

    # ── Filtrowanie ───────────────────────────────────────────────────────────

    def _apply_filters(self):
        if not self._cfg:
            return

        rows = self._all_rows
        query = self._search_var.get().strip().lower()

        if query:
            s_cols = self._cfg.get("search_cols", list(range(len(self._cfg["cols"]))))
            rows = [r for r in rows
                    if any(query in str(r[c]).lower() for c in s_cols if c < len(r))]

        for var, col_idx in zip(self._filter_vars, self._filter_col_indices):
            val = var.get().strip().lower()
            if val:
                rows = [r for r in rows if col_idx < len(r) and val in str(r[col_idx]).lower()]

        if self._sort_col is not None:
            sc = self._sort_col
            rows = sorted(rows,
                          key=lambda r: _try_num(r[sc] if sc < len(r) else ""),
                          reverse=not self._sort_asc)

        self._populate_tree(rows)

        name = self._table_var.get()
        mode = self._mode_var.get()
        mode_label = {
            "historia": "Historia",
            "M": "Aktualne – Mężczyźni",
            "W": "Aktualne – Kobiety",
            "MiW": "Aktualne – M i W",
        }.get(mode, mode)

        extra = f"  |  Tryb: {mode_label}" if name in RECORDS_TABLES else ""
        self._status_var.set(
            f"Tabela: {name}{extra}  |  "
            f"Wyświetlono: {len(rows)}  /  Wszystkich: {len(self._all_rows)}"
        )

    # ── Sortowanie ────────────────────────────────────────────────────────────

    def _sort_by(self, col_idx: int):
        if self._sort_col == col_idx:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col_idx
            self._sort_asc = True
        cols = self._cfg["cols"]
        for i, c in enumerate(cols):
            arrow = (" ▲" if self._sort_asc else " ▼") if i == self._sort_col else ""
            self._tree.heading(c, text=c + arrow)
        self._apply_filters()

    # ── Wypełnianie drzewa ────────────────────────────────────────────────────

    def _populate_tree(self, rows):
        for iid in self._tree.get_children():
            self._tree.delete(iid)

        name = self._table_var.get()
        mode = self._mode_var.get()
        use_gender_colors = (name in RECORDS_TABLES and mode == "MiW")

        # Kolumna płci w aktualnych widokach (ostatnia kolumna przed ewentualną datą)
        cols = self._cfg["cols"]
        try:
            plec_idx = cols.index("Płeć")
        except ValueError:
            plec_idx = None

        for i, row in enumerate(rows):
            vals = [("" if v is None else v) for v in row]

            if use_gender_colors and plec_idx is not None and plec_idx < len(vals):
                tag = "row_M" if str(vals[plec_idx]) == "M" else "row_W"
            else:
                tag = "odd" if i % 2 else "even"

            self._tree.insert("", "end", values=vals, tags=(tag,))

    # ── Eksport CSV ───────────────────────────────────────────────────────────

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Wszystkie", "*.*")],
            title="Zapisz jako CSV"
        )
        if not path:
            return
        import csv
        cols = self._cfg["cols"] if self._cfg else []
        rows = [self._tree.item(iid, "values") for iid in self._tree.get_children()]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
            messagebox.showinfo("Eksport", f"Zapisano {len(rows)} wierszy do:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Błąd eksportu", str(exc), parent=self)


# ── Publiczny interfejs ───────────────────────────────────────────────────────

def build_gui(parent, db_path=None):
    frame = DBViewerFrame(parent, db_path=db_path)
    return frame


# ── Standalone ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Przeglądarka bazy – manager skokow")
    root.geometry("1400x750")
    build_gui(root).pack(fill=tk.BOTH, expand=True)
    root.mainloop()
