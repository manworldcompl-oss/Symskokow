"""
liga_1vs1_tab.py  v5
====================
- Pary losowane od razu przy losowaniu grup (wszystkie 7 kolejek)
- Flagi przy zawodniku (FrozenFirstColTable) we wszystkich tabelach
- Zapis/odczyt automatyczny CSV w ./S51/Liga1v1/

INSTALACJA:
1. Wklej całą tę klasę do ski_jump_gui_full_embedded.py przed klasą MainFrame.
2. W MainFrame._build(), po nb.add(self.tab_falls, text="Upadki") dodaj:
       self.tab_liga1vs1 = ttk.Frame(nb)
       nb.add(self.tab_liga1vs1, text="Liga 1vs1")
       self._liga1vs1 = Liga1vs1Tab(self.tab_liga1vs1, main_frame=self)
       self._liga1vs1.pack(fill=tk.BOTH, expand=True)
"""

import random
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import pandas as pd


LIGA_DIR = Path("./S51/Liga1v1")


# ---------------------------------------------------------------------------
# Czysta logika
# ---------------------------------------------------------------------------

def _oblicz_punkty_meczowe(pkt_a: float, pkt_b: float):
    r = pkt_a - pkt_b
    if   r > 10:   return 3.0, 0.0
    elif r > 0:    return 2.0, 1.0
    elif r == 0:   return 1.5, 1.5
    elif r >= -10: return 1.0, 2.0
    else:          return 0.0, 3.0


def _ability(z: dict) -> float:
    try:
        return float(z.get('UM', 50)) * 0.7 + float(z.get('Forma', 50)) * 0.3
    except (TypeError, ValueError):
        return 0.0


def _losuj_grupy(zawodnicy_m: list, zawodnicy_w: list, n_grup: int = 12):
    grupy   = {}
    odcieci = {}
    for plec, lista in [('M', zawodnicy_m), ('W', zawodnicy_w)]:
        if not lista:
            for g in range(n_grup):
                grupy[(plec, g)] = []
            odcieci[plec] = []
            continue
        posort  = sorted(lista, key=_ability, reverse=True)
        rozmiar = len(posort) // n_grup
        if rozmiar % 2 == 1:
            rozmiar -= 1
        if rozmiar < 2:
            rozmiar = 2
        n_akt         = rozmiar * n_grup
        aktywni       = posort[:n_akt]
        odcieci[plec] = posort[n_akt:]
        random.shuffle(aktywni)
        koszyki = [[] for _ in range(n_grup)]
        for i, z in enumerate(aktywni):
            cykl = i // n_grup
            poz  = i % n_grup
            if cykl % 2 == 1:
                poz = n_grup - 1 - poz
            koszyki[poz].append(z)
        for g, czl in enumerate(koszyki):
            grupy[(plec, g)] = czl
    return grupy, odcieci


def _init_tabela(zawodnicy: list) -> list:
    return [{
        'zawodnik': z.get('Zawodnik', z.get('zawodnik', '')),
        'kraj':     z.get('Kraj',     z.get('kraj', '')),
        'pkt_m':    0.0,
        'wygrane':  0,
        'remisy':   0,
        'porazki':  0,
        'suma_pkt': 0.0,
        'mecze':    0,
    } for z in zawodnicy]


def _sort_tabela(tabela: list) -> list:
    return sorted(tabela, key=lambda r: (-r['pkt_m'], -r['wygrane'], -r['suma_pkt']))


def _paruj(tabela: list) -> list:
    """Losowe pary z indeksów tabeli."""
    idx = list(range(len(tabela)))
    random.shuffle(idx)
    return [(idx[i], idx[i+1]) for i in range(0, len(idx)-1, 2)]


def _pkt_map_z_cls(cls: pd.DataFrame) -> dict:
    pkt_col = next((c for c in ['Punkty','Points','Pkt','Score'] if c in cls.columns), None)
    if pkt_col is None:
        return {}
    out = {}
    for _, row in cls.iterrows():
        nazwa = str(row.get('Zawodnik', '')).strip()
        try:
            val = float(str(row[pkt_col]).replace(',', '.'))
        except (ValueError, TypeError):
            val = 0.0
        out[nazwa] = val
    return out


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def _csv_read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    for enc in ('utf-8-sig', 'utf-8', 'cp1250'):
        try:
            df = pd.read_csv(path, sep=';', encoding=enc)
            if not df.empty:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def _csv_write(path: Path, df: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep=';', index=False, encoding='utf-8-sig')


def _grupy_to_df(grupy: dict, plec: str) -> pd.DataFrame:
    wiersze = []
    for (p, nr), tabela in grupy.items():
        if p != plec:
            continue
        for r in tabela:
            wiersze.append({'grupa': nr, **r})
    return pd.DataFrame(wiersze)


def _df_to_grupy(df: pd.DataFrame, plec: str) -> dict:
    grupy = {}
    if df.empty:
        return grupy
    for nr_gr, chunk in df.groupby('grupa'):
        grupy[(plec, int(nr_gr))] = [
            {
                'zawodnik': str(r['zawodnik']),
                'kraj':     str(r['kraj']),
                'pkt_m':    float(r.get('pkt_m',    0)),
                'wygrane':  int(r.get('wygrane',  0)),
                'remisy':   int(r.get('remisy',   0)),
                'porazki':  int(r.get('porazki',  0)),
                'suma_pkt': float(r.get('suma_pkt', 0)),
                'mecze':    int(r.get('mecze',    0)),
            }
            for _, r in chunk.iterrows()
        ]
    return grupy


def _pary_to_df(pary: dict, plec: str) -> pd.DataFrame:
    wiersze = []
    for (p, nr_gr, nr_kol), lista in pary.items():
        if p != plec:
            continue
        for ia, ib in lista:
            wiersze.append({'grupa': nr_gr, 'kolejka': nr_kol, 'ia': ia, 'ib': ib})
    return pd.DataFrame(wiersze)


def _df_to_pary(df: pd.DataFrame, plec: str) -> dict:
    pary = {}
    if df.empty:
        return pary
    for _, r in df.iterrows():
        klucz = (plec, int(r['grupa']), int(r['kolejka']))
        pary.setdefault(klucz, []).append((int(r['ia']), int(r['ib'])))
    return pary


def _odcieci_to_df(odcieci: list) -> pd.DataFrame:
    return pd.DataFrame([
        {'zawodnik': z.get('Zawodnik', z.get('zawodnik', '')),
         'kraj':     z.get('Kraj',     z.get('kraj', ''))}
        for z in odcieci
    ])


def _df_to_odcieci(df: pd.DataFrame) -> list:
    if df.empty:
        return []
    return [{'Zawodnik': str(r['zawodnik']), 'Kraj': str(r['kraj'])}
            for _, r in df.iterrows()]


def _klasyf_to_df(klasyf: list) -> pd.DataFrame:
    return pd.DataFrame(klasyf) if klasyf else pd.DataFrame(
        columns=['Miejsce', 'Zawodnik', 'Kraj', 'Finał']
    )


def _df_to_klasyf(df: pd.DataFrame) -> list:
    if df.empty:
        return []
    # Normalizuj nazwy kolumn – CSV może mieć różne encodingi nagłówka 'Finał'
    rename = {}
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in ('final', 'finał', 'fina\u0142', 'fin'):
            rename[c] = 'Finał'
        elif cl in ('miejsce', 'place', 'pos'):
            rename[c] = 'Miejsce'
        elif cl in ('zawodnik', 'jumper', 'name'):
            rename[c] = 'Zawodnik'
        elif cl in ('kraj', 'nat', 'country'):
            rename[c] = 'Kraj'
    if rename:
        df = df.rename(columns=rename)
    # Upewnij się że Miejsce jest int
    if 'Miejsce' in df.columns:
        df['Miejsce'] = pd.to_numeric(df['Miejsce'], errors='coerce').fillna(0).astype(int)
    return df.to_dict('records')


# ---------------------------------------------------------------------------
# Helper: FrozenFirstColTable z flagami (wrapper dla Liga1vs1)
# ---------------------------------------------------------------------------

def _make_flag_table(parent, frozen_col='Mce') -> 'FrozenFirstColTable':
    """Tworzy FrozenFirstColTable z flagami przy Zawodniku."""
    t = FrozenFirstColTable(parent, frozen_col=frozen_col)
    t.enable_flags_after_name(FLAGS_DIR, kraj_col='Kraj', name_col='Zawodnik')
    t.pack(fill=tk.BOTH, expand=True)
    return t


def _df_tabela(tabela: list) -> pd.DataFrame:
    """Konwertuje tabelę grupy do DataFrame gotowego do wyświetlenia."""
    wiersze = []
    for i, r in enumerate(_sort_tabela(tabela), 1):
        wiersze.append({
            'Mce':      i,
            'Zawodnik': r['zawodnik'],
            'Kraj':     r['kraj'],
            'Pkt M':    r['pkt_m'],
            'W':        r['wygrane'],
            'R':        r['remisy'],
            'P':        r['porazki'],
            'Suma pkt': round(r['suma_pkt'], 1),
            'Mecze':    r['mecze'],
        })
    return pd.DataFrame(wiersze)


def _df_mecze(pary: list, tabela: list):
    """Zwraca (df_a, df_b) – lewa i prawa tabela par."""
    wiersze_a, wiersze_b = [], []
    for i, (ia, ib) in enumerate(pary, 1):
        a = tabela[ia] if ia < len(tabela) else {}
        b = tabela[ib] if ib < len(tabela) else {}
        wiersze_a.append({
            'Nr':         i,
            'Zawodnik A': a.get('zawodnik', '?'),
            'Kraj A':     a.get('kraj', ''),
        })
        wiersze_b.append({
            '_dummy':     '',
            'Zawodnik B': b.get('zawodnik', '?'),
            'Kraj B':     b.get('kraj', ''),
        })
    df_a = pd.DataFrame(wiersze_a) if wiersze_a else pd.DataFrame(
        columns=['Nr', 'Zawodnik A', 'Kraj A'])
    df_b = pd.DataFrame(wiersze_b) if wiersze_b else pd.DataFrame(
        columns=['_dummy', 'Zawodnik B', 'Kraj B'])
    return df_a, df_b


# ---------------------------------------------------------------------------
# Klasa zakładki
# ---------------------------------------------------------------------------

class Liga1vs1Tab(ttk.Frame):

    N_GRUP    = 12
    N_KOLEJEK = 7
    PROG_A    = 5
    PROG_B    = 12
    PROG_C    = 24

    OFFSET = {'A': 0, 'B': 60, 'C': 120, 'D': 264}

    def __init__(self, parent, main_frame=None):
        super().__init__(parent)
        self._mf = main_frame

        self._grupy            = {}
        self._pary             = {}
        self._cls_m            = None
        self._cls_w            = None
        self._klasyfikacja     = {'M': [], 'W': []}
        self._odcieci          = {'M': [], 'W': []}
        self._roster_m         = pd.DataFrame()
        self._roster_w         = pd.DataFrame()
        self._biezaca_kolejka  = 1

        # Referencje do tabel z flagami (tworzone w _build)
        self._ft_tabela  = None
        self._ft_mecze   = None
        self._ft_mecze_b = None
        self._ft_finaly  = None
        self._ft_klasyf  = None

        self._build()
        self._auto_load()

    # -----------------------------------------------------------------------
    # ZAPIS / ODCZYT
    # -----------------------------------------------------------------------

    def _zapisz_wszystko(self):
        try:
            for plec in ['M', 'W']:
                _csv_write(LIGA_DIR / f"grupy_{plec}.csv",
                           _grupy_to_df(self._grupy, plec))
                _csv_write(LIGA_DIR / f"pary_{plec}.csv",
                           _pary_to_df(self._pary, plec))
                _csv_write(LIGA_DIR / f"odcieci_{plec}.csv",
                           _odcieci_to_df(self._odcieci.get(plec, [])))
                _csv_write(LIGA_DIR / f"klasyfikacja_{plec}.csv",
                           _klasyf_to_df(self._klasyfikacja.get(plec, [])))
        except Exception as e:
            self._var_status.set(f"⚠ Błąd zapisu CSV: {e}")

    def _auto_load(self):
        try:
            zaladowano = False
            for plec in ['M', 'W']:
                df_gr = _csv_read(LIGA_DIR / f"grupy_{plec}.csv")
                if not df_gr.empty:
                    self._grupy.update(_df_to_grupy(df_gr, plec))
                    zaladowano = True
                df_par = _csv_read(LIGA_DIR / f"pary_{plec}.csv")
                if not df_par.empty:
                    self._pary.update(_df_to_pary(df_par, plec))
                df_odc = _csv_read(LIGA_DIR / f"odcieci_{plec}.csv")
                self._odcieci[plec] = _df_to_odcieci(df_odc)
                df_kl = _csv_read(LIGA_DIR / f"klasyfikacja_{plec}.csv")
                self._klasyfikacja[plec] = _df_to_klasyf(df_kl)

            if zaladowano:
                rozegrane = [k[2] for k in self._pary] if self._pary else [0]
                self._biezaca_kolejka = min(max(rozegrane) + 1, self.N_KOLEJEK)
                self._var_kolejka.set(self._biezaca_kolejka)
                self._var_status.set(
                    f"✓ Wczytano dane z {LIGA_DIR}. Kolejka: {self._biezaca_kolejka}."
                )
                self._odswierz_terminarz()
                # Odśwież klasyfikację dla obu płci (domyślnie M widoczna)
                self._var_plec_k.set('M')
                self._odswierz_klasyf()
        except Exception as e:
            self._var_status.set(f"ℹ Brak danych ({e}).")

    # -----------------------------------------------------------------------
    # BUDOWA GUI
    # -----------------------------------------------------------------------

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=(6, 0))

        ttk.Button(top, text="① Wczytaj zawodników",
                   command=self._wczytaj).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="② Losuj grupy + pary",
                   command=self._losuj_grupy_cmd).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        ttk.Label(top, text="Zapisz wynik z Podglądu jako:").pack(side=tk.LEFT, padx=(8, 4))
        ttk.Button(top, text="♂ Mężczyźni",
                   command=lambda: self._zapisz_cls('M')).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="♀ Kobiety",
                   command=lambda: self._zapisz_cls('W')).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        ttk.Label(top, text="Kolejka:").pack(side=tk.LEFT, padx=(8, 2))
        self._var_kolejka = tk.IntVar(value=1)
        ttk.Spinbox(top, from_=1, to=self.N_KOLEJEK,
                    textvariable=self._var_kolejka, width=3).pack(side=tk.LEFT)

        ttk.Button(top, text="③ Uzupełnij wyniki (wszystkie grupy)",
                   command=self._uzupelnij_wszystkie).pack(side=tk.LEFT, padx=(8, 12))

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(top, text="💾 Zapisz",
                   command=self._zapisz_recznie).pack(side=tk.LEFT, padx=(8, 0))

        self._var_status = tk.StringVar(value="Kliknij ① aby zacząć.")
        ttk.Label(self, textvariable=self._var_status,
                  foreground='#555').pack(fill=tk.X, padx=8, pady=(2, 4))

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self._nb = nb

        self._tab_terminarz = ttk.Frame(nb)
        self._tab_finaly    = ttk.Frame(nb)
        self._tab_klasyf    = ttk.Frame(nb)

        nb.add(self._tab_terminarz, text="Terminarz / Tabele grup")
        nb.add(self._tab_finaly,    text="Finały")
        nb.add(self._tab_klasyf,    text="Klasyfikacja końcowa")

        self._build_terminarz(self._tab_terminarz)
        self._build_finaly(self._tab_finaly)
        self._build_klasyf(self._tab_klasyf)

    # -----------------------------------------------------------------------
    # Pod-zakładka: Terminarz
    # -----------------------------------------------------------------------

    def _build_terminarz(self, parent):
        filt = ttk.Frame(parent)
        filt.pack(fill=tk.X, padx=6, pady=(6, 2))

        ttk.Label(filt, text="Wyświetl:").pack(side=tk.LEFT)
        self._var_plec_t = tk.StringVar(value='M')
        ttk.Radiobutton(filt, text="Mężczyźni", variable=self._var_plec_t,
                        value='M', command=self._odswierz_terminarz).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Radiobutton(filt, text="Kobiety", variable=self._var_plec_t,
                        value='W', command=self._odswierz_terminarz).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(filt, text="Grupa:").pack(side=tk.LEFT)
        self._var_grupa_t = tk.IntVar(value=0)
        ttk.Spinbox(filt, from_=0, to=self.N_GRUP - 1,
                    textvariable=self._var_grupa_t, width=3,
                    command=self._odswierz_terminarz).pack(side=tk.LEFT, padx=(2, 8))

        ttk.Label(filt, text="Kolejka (pary):").pack(side=tk.LEFT)
        self._var_kolejka_t = tk.IntVar(value=1)
        ttk.Spinbox(filt, from_=1, to=self.N_KOLEJEK,
                    textvariable=self._var_kolejka_t, width=3,
                    command=self._odswierz_terminarz).pack(side=tk.LEFT)

        # Paned: tabela grupy | pary kolejki
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        lf_tab = ttk.LabelFrame(paned, text="Tabela grupy")
        paned.add(lf_tab, weight=2)
        self._ft_tabela = _make_flag_table(lf_tab, frozen_col='Mce')

        lf_mec = ttk.LabelFrame(paned, text="Pary wybranej kolejki")
        paned.add(lf_mec, weight=3)

        # Tabela par: 3 sekcje w jednym LabelFrame
        # [Nr] | [flaga Zawodnik A  Kraj A] | [vs] | [flaga Zawodnik B  Kraj B]
        # Realizacja: FrozenFirstColTable (Nr + ZawA) | Label vs | FrozenFirstColTable (ZawB)
        mec_frame = ttk.Frame(lf_mec)
        mec_frame.pack(fill=tk.BOTH, expand=True)
        mec_frame.columnconfigure(0, weight=3)
        mec_frame.columnconfigure(1, weight=0)
        mec_frame.columnconfigure(2, weight=3)
        mec_frame.rowconfigure(0, weight=1)

        # Lewa: Nr + Zawodnik A z flagą
        self._ft_mecze = FrozenFirstColTable(mec_frame, frozen_col='Nr')
        self._ft_mecze.enable_flags_after_name(FLAGS_DIR, kraj_col='Kraj A', name_col='Zawodnik A')
        self._ft_mecze.grid(row=0, column=0, sticky='nsew')

        # Środek: kolumna "vs" (wąska)
        vs_frame = ttk.Frame(mec_frame, width=28)
        vs_frame.grid(row=0, column=1, sticky='nsew', padx=0)
        vs_frame.pack_propagate(False)
        ttk.Label(vs_frame, text='vs', anchor='center').pack(expand=True)

        # Prawa: Zawodnik B z flagą (bez zamrożonej kolumny – Nr już jest po lewej)
        self._ft_mecze_b = FrozenFirstColTable(mec_frame, frozen_col='_dummy')
        self._ft_mecze_b.enable_flags_after_name(FLAGS_DIR, kraj_col='Kraj B', name_col='Zawodnik B')
        self._ft_mecze_b.grid(row=0, column=2, sticky='nsew')

        # Synchronizacja przewijania między lewą i prawą tabelą par
        def _sync_yview_mec(*args):
            self._ft_mecze.tv_fixed.yview_moveto(args[0])
            self._ft_mecze.tv_main.yview_moveto(args[0])
            self._ft_mecze_b.tv_fixed.yview_moveto(args[0])
            self._ft_mecze_b.tv_main.yview_moveto(args[0])

        self._ft_mecze.vsb.configure(command=_sync_yview_mec)
        self._ft_mecze_b.vsb.configure(command=_sync_yview_mec)
        self._ft_mecze.tv_main.configure(yscrollcommand=lambda *a: (
            self._ft_mecze.vsb.set(*a), _sync_yview_mec(a[0])
        ))
        self._ft_mecze_b.tv_main.configure(yscrollcommand=lambda *a: (
            self._ft_mecze_b.vsb.set(*a), _sync_yview_mec(a[0])
        ))

    # -----------------------------------------------------------------------
    # Pod-zakładka: Finały
    # -----------------------------------------------------------------------

    def _build_finaly(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=6, pady=(6, 4))

        ttk.Label(top, text="Płeć:").pack(side=tk.LEFT)
        self._var_plec_f = tk.StringVar(value='M')
        ttk.Radiobutton(top, text="M", variable=self._var_plec_f,
                        value='M').pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(top, text="W", variable=self._var_plec_f,
                        value='W').pack(side=tk.LEFT, padx=(0, 12))

        opisy = {
            'A': f"TOP {self.PROG_A}",
            'B': f"mce {self.PROG_A+1}–{self.PROG_B}",
            'C': f"mce {self.PROG_B+1}–{self.PROG_C}",
            'D': f"mce {self.PROG_C+1}+",
        }
        for lit in ['A', 'B', 'C', 'D']:
            ttk.Button(
                top,
                text=f"Lista Finału {lit}  ({opisy[lit]})",
                command=lambda l=lit: self._pokaz_liste_finalu(l)
            ).pack(side=tk.LEFT, padx=(0, 4))

        lf = ttk.LabelFrame(parent, text="Lista startowa finału")
        lf.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self._ft_finaly = _make_flag_table(lf, frozen_col='Gr.')

    # -----------------------------------------------------------------------
    # Pod-zakładka: Klasyfikacja końcowa
    # -----------------------------------------------------------------------

    def _build_klasyf(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=6, pady=(6, 4))

        ttk.Label(top, text="Płeć:").pack(side=tk.LEFT)
        self._var_plec_k = tk.StringVar(value='M')
        ttk.Radiobutton(top, text="M", variable=self._var_plec_k, value='M',
                        command=self._odswierz_klasyf).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(top, text="W", variable=self._var_plec_k, value='W',
                        command=self._odswierz_klasyf).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(top, text="Uzupełnij z Podglądu →").pack(side=tk.LEFT)
        for lit in ['A', 'B', 'C', 'D']:
            ttk.Button(
                top, text=f"Finał {lit}",
                command=lambda l=lit: self._uzupelnij_final_klasyf(l)
            ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(top, text="Wyczyść",
                   command=self._wyczysc_klasyf).pack(side=tk.LEFT, padx=(16, 0))

        lf = ttk.LabelFrame(parent, text="Klasyfikacja końcowa turnieju")
        lf.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self._ft_klasyf = _make_flag_table(lf, frozen_col='Miejsce')

    # -----------------------------------------------------------------------
    # ① Wczytaj zawodników
    # -----------------------------------------------------------------------

    def _wczytaj(self):
        if self._mf is None:
            messagebox.showerror("Błąd", "Brak MainFrame."); return

        df = None
        try:
            sel = getattr(self._mf, 'selected_df', None)
            if sel is not None and not sel.empty:
                df = sel.copy()
        except Exception:
            pass

        if df is None or df.empty:
            try:
                import ski_jump_simulator_random_v6 as sim
                df = sim.load_roster(Path(self._mf.var_excel.get().strip()))
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można wczytać:\n{e}"); return

        if df is None or df.empty:
            messagebox.showerror("Błąd", "Brak zawodników."); return

        plec_col = next(
            (c for c in ['Płeć', 'Plec', 'Sex', 'Gender'] if c in df.columns), None
        )
        if plec_col is None:
            messagebox.showwarning("Uwaga", "Brak kolumny płci – wszyscy jako M.")
            self._roster_m = df.copy()
            self._roster_w = pd.DataFrame(columns=df.columns)
        else:
            m = df[plec_col].astype(str).str.upper().isin(['M', 'MAN', 'MALE', 'MĘŻCZYZNA'])
            w = df[plec_col].astype(str).str.upper().isin(['W', 'K', 'F', 'WOMAN', 'FEMALE', 'KOBIETA'])
            self._roster_m = df[m].reset_index(drop=True)
            self._roster_w = df[w].reset_index(drop=True)

        self._var_status.set(
            f"✓ Wczytano: {len(self._roster_m)} M, {len(self._roster_w)} W. Kliknij ②."
        )

    # -----------------------------------------------------------------------
    # ② Losuj grupy + wszystkie pary od razu
    # -----------------------------------------------------------------------

    def _losuj_grupy_cmd(self):
        if self._roster_m.empty and self._roster_w.empty:
            messagebox.showwarning("Uwaga", "Najpierw wczytaj zawodników (①)."); return

        if self._grupy:
            if not messagebox.askyesno(
                "Uwaga",
                "Istnieją już dane.\nLosowanie usunie wszystkie wyniki. Kontynuować?"
            ):
                return

        self._grupy        = {}
        self._pary         = {}
        self._odcieci      = {'M': [], 'W': []}
        self._klasyfikacja = {'M': [], 'W': []}

        grupy, odcieci = _losuj_grupy(
            self._roster_m.to_dict('records'),
            self._roster_w.to_dict('records'),
            self.N_GRUP
        )
        for (plec, nr), czl in grupy.items():
            self._grupy[(plec, nr)] = _init_tabela(czl)
        self._odcieci = odcieci

        # Wylosuj pary na WSZYSTKIE kolejki od razu
        for (plec, nr), tabela in self._grupy.items():
            for kol in range(1, self.N_KOLEJEK + 1):
                self._pary[(plec, nr, kol)] = _paruj(tabela)

        info_parts = []
        for plec in ['M', 'W']:
            sizes = [len(self._grupy.get((plec, g), [])) for g in range(self.N_GRUP)]
            n_odc = len(odcieci.get(plec, []))
            info_parts.append(
                f"{'M' if plec=='M' else 'W'}: {self.N_GRUP}×{sizes[0] if sizes else 0}"
                f", odcięto {n_odc}"
            )

        self._biezaca_kolejka = 1
        self._var_kolejka.set(1)
        self._zapisz_wszystko()
        self._var_status.set(
            "✓ " + " | ".join(info_parts) +
            f". Pary na {self.N_KOLEJEK} kolejek wylosowane. Kliknij ③ po uzupełnieniu wyników."
        )
        self._odswierz_terminarz()

    # -----------------------------------------------------------------------
    # Zapisz wynik z Podglądu
    # -----------------------------------------------------------------------

    def _zapisz_cls(self, plec: str):
        if self._mf is None:
            messagebox.showerror("Błąd", "Brak MainFrame."); return
        cls = getattr(self._mf, '_last_final_cls', None)
        if cls is None or not isinstance(cls, pd.DataFrame) or cls.empty:
            messagebox.showerror("Błąd", "Brak wyników w Podglądzie."); return
        if plec == 'M':
            self._cls_m = cls.copy()
            self._var_status.set(f"✓ Wynik zapisany jako MĘŻCZYŹNI ({len(cls)} zawodników).")
        else:
            self._cls_w = cls.copy()
            self._var_status.set(f"✓ Wynik zapisany jako KOBIETY ({len(cls)} zawodników).")

    # -----------------------------------------------------------------------
    # ③ Uzupełnij wyniki
    # -----------------------------------------------------------------------

    def _uzupelnij_wszystkie(self):
        nr_kol = self._var_kolejka.get()

        brak = []
        if self._cls_m is None: brak.append("M  (kliknij ♂ Mężczyźni)")
        if self._cls_w is None: brak.append("W  (kliknij ♀ Kobiety)")
        if brak:
            messagebox.showwarning(
                "Brak wyników",
                "Najpierw zapisz wyniki z Podglądu:\n" + "\n".join(f"  • {b}" for b in brak)
            ); return

        pm_m = _pkt_map_z_cls(self._cls_m)
        pm_w = _pkt_map_z_cls(self._cls_w)
        bledy = []
        uzupelnione = 0

        for (plec, nr_gr), tabela in self._grupy.items():
            klucz_par = (plec, nr_gr, nr_kol)
            if klucz_par not in self._pary:
                continue
            pm = pm_m if plec == 'M' else pm_w
            for ia, ib in self._pary[klucz_par]:
                a, b = tabela[ia], tabela[ib]
                pa = pm.get(a['zawodnik'])
                pb = pm.get(b['zawodnik'])
                if pa is None or pb is None:
                    bledy.append(f"{a['zawodnik']} vs {b['zawodnik']} ({plec} gr.{nr_gr})")
                    continue
                pma, pmb = _oblicz_punkty_meczowe(pa, pb)
                a['pkt_m'] += pma;   b['pkt_m'] += pmb
                a['suma_pkt'] += pa; b['suma_pkt'] += pb
                a['mecze'] += 1;     b['mecze'] += 1
                if pma > pmb:   a['wygrane'] += 1; b['porazki'] += 1
                elif pmb > pma: b['wygrane'] += 1; a['porazki'] += 1
                else:           a['remisy']  += 1; b['remisy']  += 1
                uzupelnione += 1

        self._cls_m = None
        self._cls_w = None

        if nr_kol < self.N_KOLEJEK:
            self._var_kolejka.set(nr_kol + 1)
            next_info = f" Następna: {nr_kol + 1}."
        else:
            next_info = " Faza grupowa zakończona!"

        self._zapisz_wszystko()
        info = f"✓ Kolejka {nr_kol}: {uzupelnione} meczów."
        if bledy:
            info += f" ⚠ Brak {len(bledy)} zawodników."
        self._var_status.set(info + next_info)
        self._odswierz_terminarz()

    # -----------------------------------------------------------------------
    # Finały – lista startowa
    # -----------------------------------------------------------------------

    def _pokaz_liste_finalu(self, litera: str):
        if not self._grupy:
            messagebox.showwarning("Uwaga", "Brak danych grup."); return

        plec = self._var_plec_f.get()
        zakresy = {
            'A': (1,             self.PROG_A),
            'B': (self.PROG_A+1, self.PROG_B),
            'C': (self.PROG_B+1, self.PROG_C),
            'D': (self.PROG_C+1, 9999),
        }
        od, do = zakresy[litera]

        wiersze = []
        for nr_gr in range(self.N_GRUP):
            tab = self._grupy.get((plec, nr_gr))
            if tab is None: continue
            for poz, r in enumerate(_sort_tabela(tab), 1):
                if od <= poz <= do:
                    wiersze.append({
                        'Gr.':       nr_gr,
                        'Mce w gr.': poz,
                        'Zawodnik':  r['zawodnik'],
                        'Kraj':      r['kraj'],
                        'Pkt M':     r['pkt_m'],
                        'W':         r['wygrane'],
                        'R':         r['remisy'],
                        'P':         r['porazki'],
                        'Suma pkt':  round(r['suma_pkt'], 1),
                    })

        wiersze.sort(key=lambda r: (-r['Pkt M'], -r['W'], -r['Suma pkt']))
        df = pd.DataFrame(wiersze) if wiersze else pd.DataFrame()
        self._ft_finaly.set_dataframe(df)
        self._nb.select(self._tab_finaly)
        self._var_status.set(
            f"Lista Finału {litera} | {'M' if plec=='M' else 'W'} – {len(wiersze)} zawodników."
        )

    # -----------------------------------------------------------------------
    # Klasyfikacja końcowa
    # -----------------------------------------------------------------------

    def _uzupelnij_final_klasyf(self, litera: str):
        plec = self._var_plec_k.get()
        cls  = self._cls_m if plec == 'M' else self._cls_w

        if cls is None or cls.empty:
            raw = getattr(self._mf, '_last_final_cls', None) if self._mf else None
            if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
                messagebox.showerror(
                    "Brak wyników",
                    f"Brak wyniku dla {'M' if plec=='M' else 'W'}.\n"
                    "Uruchom konkurs, potem kliknij ♂/♀."
                ); return
            cls = raw

        zakresy = {
            'A': (1,             self.PROG_A),
            'B': (self.PROG_A+1, self.PROG_B),
            'C': (self.PROG_B+1, self.PROG_C),
            'D': (self.PROG_C+1, 9999),
        }
        od, do = zakresy[litera]

        uprawnieni = set()
        for nr_gr in range(self.N_GRUP):
            tab = self._grupy.get((plec, nr_gr))
            if tab is None: continue
            for poz, r in enumerate(_sort_tabela(tab), 1):
                if od <= poz <= do:
                    uprawnieni.add(r['zawodnik'])

        if not uprawnieni:
            messagebox.showwarning("Uwaga", "Brak uprawnionych – przeprowadź fazę grupową."); return

        cls_filtered = cls[
            cls['Zawodnik'].astype(str).str.strip().isin(uprawnieni)
        ].reset_index(drop=True)

        if cls_filtered.empty:
            messagebox.showwarning(
                "Uwaga",
                f"Żaden z {len(uprawnieni)} uprawnionych nie pojawił się w wynikach."
            ); return

        offset = self.OFFSET.get(litera, 0)

        self._klasyfikacja[plec] = [
            w for w in self._klasyfikacja[plec] if w['Finał'] != litera
        ]
        for i, (_, row) in enumerate(cls_filtered.iterrows(), 1):
            self._klasyfikacja[plec].append({
                'Miejsce':  offset + i,
                'Zawodnik': str(row.get('Zawodnik', '')),
                'Kraj':     str(row.get('Kraj', '')),
                'Finał':    litera,
            })

        if litera == 'D':
            odcieci    = self._odcieci.get(plec, [])
            ostatnie   = max((w['Miejsce'] for w in self._klasyfikacja[plec]), default=self.OFFSET['D'])
            istniejace = {w['Zawodnik'] for w in self._klasyfikacja[plec]}
            for i, z in enumerate(odcieci, 1):
                nazwa = z.get('Zawodnik', z.get('zawodnik', ''))
                kraj  = z.get('Kraj',     z.get('kraj', ''))
                if nazwa not in istniejace:
                    self._klasyfikacja[plec].append({
                        'Miejsce':  ostatnie + i,
                        'Zawodnik': nazwa,
                        'Kraj':     kraj,
                        'Finał':    'D (odcięci)',
                    })

        self._klasyfikacja[plec].sort(key=lambda x: x['Miejsce'])
        self._zapisz_wszystko()
        self._odswierz_klasyf()

        n_odc = len(self._odcieci.get(plec, []))
        self._var_status.set(
            f"✓ Klasyfikacja {'M' if plec=='M' else 'W'} – Finał {litera}: "
            f"{len(cls_filtered)} zawodników"
            + (f" + {n_odc} odciętych." if litera == 'D' and n_odc else ".")
            + f" Łącznie: {len(self._klasyfikacja[plec])}."
        )

    def _wyczysc_klasyf(self):
        plec = self._var_plec_k.get()
        if messagebox.askyesno("Potwierdź", f"Wyczyścić klasyfikację {'M' if plec=='M' else 'W'}?"):
            self._klasyfikacja[plec] = []
            self._zapisz_wszystko()
            self._odswierz_klasyf()

    def _zapisz_recznie(self):
        self._zapisz_wszystko()
        self._var_status.set(f"✓ Zapisano do {LIGA_DIR}/")

    # -----------------------------------------------------------------------
    # Odświeżanie widoków
    # -----------------------------------------------------------------------

    def _odswierz_terminarz(self, *_):
        plec   = self._var_plec_t.get()
        nr_gr  = self._var_grupa_t.get()
        nr_kol = self._var_kolejka_t.get()

        tab = self._grupy.get((plec, nr_gr), [])

        # Tabela grupy
        df_tab = _df_tabela(tab)
        if self._ft_tabela is not None:
            self._ft_tabela.set_dataframe(df_tab)

        # Pary kolejki
        pary = self._pary.get((plec, nr_gr, nr_kol), [])
        df_a, df_b = _df_mecze(pary, tab)
        if self._ft_mecze is not None:
            self._ft_mecze.set_dataframe(df_a)
        if self._ft_mecze_b is not None:
            self._ft_mecze_b.set_dataframe(df_b)

    def _odswierz_klasyf(self, *_):
        plec = self._var_plec_k.get()
        dane = self._klasyfikacja.get(plec, [])
        df   = pd.DataFrame(dane) if dane else pd.DataFrame(
            columns=['Miejsce', 'Zawodnik', 'Kraj', 'Finał']
        )
        if self._ft_klasyf is not None:
            self._ft_klasyf.set_dataframe(df)
