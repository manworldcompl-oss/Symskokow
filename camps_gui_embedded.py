import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import random
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
FLAGS_DIR = APP_DIR / "flags"

# --- KONFIGURACJA ---
CAMPS = [("Schtchutchinsk", "KAZ", 10, 10), ("Oslo", "NOR", 10, 9), ("Lahti", "FIN", 9, 10), ("Zakopane", "POL", 9, 9)]
UO_AGE_M = {(0, 14): 5, (15, 18): 4, (19, 21): 3, (22, 24): 2, (25, 27): 1, (28, 30): 0, (31, 32): -1, (33, 34): -2, (35, 36): -3, (37, 39): -4, (40, 99): -5}
UO_AGE_W = {(0, 15): 5, (16, 18): 4, (19, 21): 3, (22, 25): 2, (26, 28): 1, (29, 31): 0, (32, 33): -1, (34, 35): -2, (36, 37): -3, (38, 39): -4, (40, 99): -5}
FO_AGE = {(0, 14): 5, (15, 18): 4, (19, 21): 3, (22, 24): 2, (25, 27): 1, (28, 30): 0, (31, 32): -1, (33, 34): -2, (35, 36): -3, (37, 39): -4, (40, 99): -5}

COACH_PRICE_TAB = [(94, 100, 100000), (87, 93, 95000), (79, 86, 90000), (71, 78, 85000), (63, 70, 80000), (55, 62, 75000), (47, 54, 70000), (39, 46, 65000), (31, 38, 60000), (21, 30, 55000), (1, 20, 50000)]
UM_PRICE_TAB = [(80, 100, 100000), (75, 79, 90000), (70, 74, 85000), (65, 69, 80000), (60, 64, 75000), (55, 59, 70000), (50, 54, 65000), (35, 49, 60000), (25, 34, 55000), (0, 24, 50000)]
FORMA_PRICE_TAB = [(80, 100, 100000), (75, 79, 90000), (70, 74, 85000), (65, 69, 80000), (60, 64, 75000), (55, 59, 70000), (50, 54, 65000), (35, 49, 60000), (25, 34, 55000), (0, 24, 50000)]

def get_tab_val(val, table):
    try:
        v = float(val)
        for low, high, price in table:
            if low <= v <= high: return price
    except: pass
    return 50000

def get_age_pts(age, table_dict):
    for (low, high), pts in table_dict.items():
        if low <= age <= high: return pts
    return 0

class CampsModule(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)
        
        self.tab_sel = ttk.Frame(self.nb)
        self.tab_calc = ttk.Frame(self.nb)
        self.tab_summary = ttk.Frame(self.nb)
        
        self.nb.add(self.tab_sel, text="Wybór zawodników")
        self.nb.add(self.tab_calc, text="Lista obozowa")
        self.nb.add(self.tab_summary, text="Podsumowanie finansowe")
        
        self.players_path = str(APP_DIR / "S51" / "Zawodnicy S51gpt.csv")
        self.camps_path   = str(APP_DIR / "S51" / "Obozy Szkoleniowe S51.csv")
        self.costs_path   = str(APP_DIR / "S51" / "Koszty Obozu S51.csv")
        
        self._flag_cache = {}
        self._blank_flag = tk.PhotoImage(width=20, height=13)  # puste 20x13
        self.staff_m = self._smart_load_staff("Sztab M S51.csv")
        self.staff_w = self._smart_load_staff("Sztab W S51.csv")
        self.selected_players_data = []

        self._setup_selection_tab()
        self._setup_calc_tab()
        self._setup_summary_tab()
        
        self._load_existing_camp_report()
        self.load_players_list()

    # ── Flagi ────────────────────────────────────────────────────────────────
    def _get_flag(self, nat_code: str):
        """Zwraca tk.PhotoImage dla kodu kraju lub None."""
        if not nat_code:
            return self._blank_flag
        code = str(nat_code).strip().lower()
        if code in self._flag_cache:
            return self._flag_cache[code]
        path = FLAGS_DIR / f"{code}.png"
        if path.exists():
            try:
                img = tk.PhotoImage(file=str(path))
                self._flag_cache[code] = img
                return img
            except Exception:
                pass
        self._flag_cache[code] = self._blank_flag
        return self._blank_flag

    def _smart_load_staff(self, filename):
        paths = [str(APP_DIR / "S51" / filename), str(APP_DIR / filename), filename]
        for p in paths:
            if os.path.exists(p):
                for enc in ['cp1250', 'utf-8-sig']:
                    try:
                        df = pd.read_csv(p, sep=";", encoding=enc)
                        df.columns = [str(c).strip().replace('\ufeff', '') for c in df.columns]
                        if 'UM' in df.columns:
                            df['UM'] = pd.to_numeric(df['UM'].astype(str).str.replace(r'\s+', '', regex=True), errors='coerce')
                        return df
                    except: continue
        return pd.DataFrame()

    def _clean_numeric(self, val):
        try:
            if pd.isna(val): return 0.0
            s = str(val).replace(' ', '').replace(',', '').strip()
            return float(s)
        except: return 0.0

    def _load_existing_camp_report(self):
        if os.path.exists(self.camps_path):
            try:
                for s in [';', ',']:
                    df = pd.read_csv(self.camps_path, sep=s, encoding='utf-8-sig')
                    if len(df.columns) > 5: break
                df.columns = [c.strip() for c in df.columns]
                self.selected_players_data = []
                for _, row in df.iterrows():
                    self.selected_players_data.append({
                        'Zawodnik': row['Zawodnik'],
                        'Kraj': str(row['Kraj']).strip().upper(),
                        'Płeć': row['Płeć'],
                        'Wiek': int(row['Wiek']),
                        'UM': self._clean_numeric(row['UM PRZED']),
                        'Forma': self._clean_numeric(row['Forma PRZED'])
                    })
                self.refresh_calc_table()
            except Exception as e: print(f"Błąd wczytywania raportu: {e}")

    def treeview_sort_column(self, tv, col, reverse):
        """Funkcja do sortowania kolumn w Treeview."""
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
        
        # Próba sortowania numerycznego
        try:
            l.sort(key=lambda t: float(t[0].replace(',', '').replace(' ', '').replace('€', '')), reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            tv.move(k, '', index)

        tv.heading(col, command=lambda: self.treeview_sort_column(tv, col, not reverse))

    def _setup_selection_tab(self):
        f = ttk.Frame(self.tab_sel, padding=10)
        f.pack(fill=tk.BOTH, expand=True)
        cols = ("Zawodnik", "Kraj", "Płeć", "Wiek", "UM", "Forma")
        
        self.tree_sel = ttk.Treeview(f, columns=cols, show="tree headings", selectmode="extended")
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tree_sel.yview)
        self.tree_sel.configure(yscrollcommand=vsb.set)

        # #0 = Zawodnik z flagą; ukrywamy kolumnę "Zawodnik"
        self.tree_sel.heading("#0", text="Zawodnik")
        self.tree_sel.column("#0", width=220, stretch=True, anchor=tk.W)
        for c in cols:
            self.tree_sel.heading(c, text=c, command=lambda _c=c: self.treeview_sort_column(self.tree_sel, _c, False))
            self.tree_sel.column(c, width=120)
        self.tree_sel.column("Zawodnik", width=0, stretch=False)  # ukryta
        
        self.tree_sel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_sel.bind("<<TreeviewSelect>>", lambda e: self._update_sel_counter())

        ttk.Button(self.tab_sel, text="Dodaj do obozu >>", command=self.move_to_camp).pack(pady=5)
        self.sel_counter_var = tk.StringVar(value="Zaznaczonych: 0  (M: 0 | W: 0)")
        ttk.Label(self.tab_sel, textvariable=self.sel_counter_var, font=("TkDefaultFont", 9, "bold")).pack(pady=(0, 6))

    def load_players_list(self):
        for i in self.tree_sel.get_children(): self.tree_sel.delete(i)
        if not os.path.exists(self.players_path): return
        df = pd.read_csv(self.players_path)
        selected_names = [p['Zawodnik'] for p in self.selected_players_data]
        for _, p in df.iterrows():
            if p['Zawodnik'] not in selected_names:
                flag = self._get_flag(p['Kraj'])
                self.tree_sel.insert("", "end", text=' ' + p['Zawodnik'], image=flag,
                    values=(p['Zawodnik'], p['Kraj'], p['Płeć'], p['Wiek'], p['UM'], p['Forma']))

    def _update_sel_counter(self):
        selected = self.tree_sel.selection()
        m_count = sum(1 for iid in selected if self.tree_sel.set(iid, "Płeć") == "M")
        w_count = sum(1 for iid in selected if self.tree_sel.set(iid, "Płeć") == "W")
        total = len(selected)
        self.sel_counter_var.set(f"Zaznaczonych: {total}  (M: {m_count} | W: {w_count})")

    def move_to_camp(self):
        for iid in self.tree_sel.selection():
            v = self.tree_sel.item(iid, 'values')
            self.selected_players_data.append({
                'Zawodnik': v[0], 'Kraj': str(v[1]).strip().upper(), 
                'Płeć': v[2], 'Wiek': int(v[3]), 'UM': float(v[4]), 'Forma': float(v[5])
            })
        self.load_players_list(); self.refresh_calc_table()

    def _setup_calc_tab(self):
        f = ttk.Frame(self.tab_calc, padding=5)
        f.pack(fill=tk.BOTH, expand=True)
        self.calc_cols = ("Lp.", "Lp.2", "Zawodnik", "Kraj", "Wiek", "Płeć", "UM PRZED", "Forma PRZED", 
                    "Losowanie UM", "Losowanie Formy", "Obóz", "UMO", "FormaO", "Trener", 
                    "UO", "FO", "UPO", "FPO", "Cena wstępna", "Cena")
        self.tree_calc = ttk.Treeview(f, columns=self.calc_cols, show="tree headings")
        # #0 = Lp. z flagą; ukrywamy kolumnę "Lp."
        self.tree_calc.heading("#0", text="Lp.")
        self.tree_calc.column("#0", width=55, stretch=False, anchor=tk.CENTER)
        for c in self.calc_cols:
            self.tree_calc.heading(c, text=c, command=lambda _c=c: self.treeview_sort_column(self.tree_calc, _c, False))
            self.tree_calc.column(c, width=80, anchor=tk.CENTER)
        self.tree_calc.column("Lp.", width=0, stretch=False)  # ukryta
        
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tree_calc.yview)
        hsb = ttk.Scrollbar(f, orient="horizontal", command=self.tree_calc.xview)
        self.tree_calc.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree_calc.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns"); hsb.grid(row=1, column=0, sticky="ew")
        f.grid_columnconfigure(0, weight=1); f.grid_rowconfigure(0, weight=1)
        
        btn_f = ttk.Frame(self.tab_calc)
        btn_f.pack(fill=tk.X)
        ttk.Button(btn_f, text="<< Usuń z obozu", command=self.remove_from_camp).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(btn_f, text="ZAPISZ I AKTUALIZUJ BAZĘ", command=self.update_main_database).pack(side=tk.RIGHT, padx=5, pady=5)
        ttk.Button(btn_f, text="ZAPISZ RAPORT OBOZU", command=self.save_camp_report).pack(side=tk.RIGHT, padx=5, pady=5)

    def remove_from_camp(self):
        selected = self.tree_calc.selection()
        if not selected: return
        indices = sorted([self.tree_calc.index(i) for i in selected], reverse=True)
        for idx in indices: self.selected_players_data.pop(idx)
        self.load_players_list(); self.refresh_calc_table()

    def refresh_calc_table(self):
        for i in self.tree_calc.get_children(): self.tree_calc.delete(i)
        self.selected_players_data.sort(key=lambda x: (x['Kraj'], x['Zawodnik']))
        kraj_counts = {}

        for i, p in enumerate(self.selected_players_data):
            kraj, sex, age = p['Kraj'], p['Płeć'], p['Wiek']
            kraj_counts[kraj] = kraj_counts.get(kraj, 0) + 1
            lp2 = kraj_counts[kraj]
            c_name, c_kraj, umo, formao = CAMPS[0]
            l_um, l_f = random.randint(-3, 3), random.randint(-3, 3)
            
            st_df = self.staff_m if sex == 'M' else self.staff_w
            coach_um = 20.0
            if not st_df.empty:
                m = st_df[(st_df['NAT'].str.upper() == kraj) & (st_df['Code'].str.upper() == ('TJ' if age < 18 else 'TS'))]
                if not m.empty: coach_um = float(m.iloc[0]['UM'])

            uo = round(umo * (0.25 if sex=='M' else 0.2) + coach_um * (0.125 if sex=='M' else 0.1) + get_age_pts(age, UO_AGE_M if sex=='M' else UO_AGE_W) + l_um)
            fo = round(formao * 0.3 + coach_um * 0.15 + get_age_pts(age, FO_AGE) + l_f)
            
            p['UPO_FINAL'] = p['UM'] + uo
            p['FPO_FINAL'] = p['Forma'] + fo
            p['UO_CALC'], p['FO_CALC'] = uo, fo
            p['L_UM'], p['L_F'], p['C_UM'] = l_um, l_f, coach_um

            c_wst = get_tab_val(coach_um, COACH_PRICE_TAB) + get_tab_val(p['UM'], UM_PRICE_TAB) + get_tab_val(p['Forma'], FORMA_PRICE_TAB)
            cena = c_wst + ((lp2 - 20) * 25000 if lp2 > 20 else (-(11 - lp2) * 5000 if lp2 < 11 else 0))
            p['CENA_WST'], p['CENA_FINAL'], p['LP2'] = c_wst, cena, lp2

            flag = self._get_flag(kraj)
            self.tree_calc.insert("", "end", text=' ' + str(i+1), image=flag, values=(
                i+1, lp2, p['Zawodnik'], kraj, age, sex, p['UM'], p['Forma'],
                l_um, l_f, c_name, umo, formao, coach_um, uo, fo, p['UPO_FINAL'], p['FPO_FINAL'],
                f"{int(c_wst):,} €", f"{int(cena):,} €"
            ))
        self.update_summary_view()

    def _setup_summary_tab(self):
        f = ttk.Frame(self.tab_summary, padding=10)
        f.pack(fill=tk.BOTH, expand=True)

        sum_cols = ("Kraj", "M", "W", "Razem", "Koszt łączny")
        self.tree_summary = ttk.Treeview(f, columns=sum_cols, show="tree headings")
        # #0 = Kraj z flagą; ukrywamy kolumnę "Kraj"
        self.tree_summary.heading("#0", text="Kraj")
        self.tree_summary.column("#0", width=100, stretch=False, anchor=tk.W)
        col_widths = {"Kraj": 0, "M": 50, "W": 50, "Razem": 60, "Koszt łączny": 160}
        for c in sum_cols:
            self.tree_summary.heading(c, text=c, command=lambda _c=c: self.treeview_sort_column(self.tree_summary, _c, False))
            self.tree_summary.column(c, width=col_widths.get(c, 80), anchor=tk.CENTER, stretch=(c != "Kraj"))
        self.tree_summary.column("Kraj", width=0, stretch=False)  # ukryta

        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tree_summary.yview)
        self.tree_summary.configure(yscrollcommand=vsb.set)
        self.tree_summary.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Button(self.tab_summary, text="EKSPORTUJ KOSZTY OBOZU (.CSV)", command=self.export_financial_csv).pack(pady=5)

    def update_summary_view(self):
        for row in self.tree_summary.get_children():
            self.tree_summary.delete(row)
        if not self.selected_players_data:
            return
        df = pd.DataFrame(self.selected_players_data)
        summ = df.groupby('Kraj').agg(
            M=('Płeć', lambda x: (x == 'M').sum()),
            W=('Płeć', lambda x: (x == 'W').sum()),
            Razem=('Płeć', 'count'),
            Koszt=('CENA_FINAL', 'sum')
        ).reset_index()
        for _, r in summ.iterrows():
            flag = self._get_flag(r['Kraj'])
            self.tree_summary.insert("", "end", text=' ' + str(r['Kraj']), image=flag,
                values=(r['Kraj'], int(r['M']), int(r['W']), int(r['Razem']), f"{int(r['Koszt']):,} €"))
        # Wiersz sumy
        self.tree_summary.insert("", "end", text="SUMA",
            values=("SUMA", "", "", int(summ['Razem'].sum()), f"{int(summ['Koszt'].sum()):,} €"),
            tags=("suma",))
        self.tree_summary.tag_configure("suma", font=("TkDefaultFont", 9, "bold"))

    def export_financial_csv(self):
        if not self.selected_players_data: return
        df = pd.DataFrame(self.selected_players_data)
        summ = df.groupby('Kraj').agg(
            Liczba_M=('Płeć', lambda x: (x == 'M').sum()),
            Liczba_W=('Płeć', lambda x: (x == 'W').sum()),
            Razem=('Płeć', 'count'),
            Koszt=('CENA_FINAL', 'sum')
        ).reset_index()
        summ.to_csv(self.costs_path, index=False, sep=';', encoding='utf-8-sig')
        messagebox.showinfo("Eksport", f"Zapisano koszty w: {self.costs_path}")

    def save_camp_report(self):
        if not self.selected_players_data: return
        if not messagebox.askyesno("Zapis", f"Czy zapisać raport obozu do:\n{self.camps_path}?"): return

        export_list = []
        for i, p in enumerate(self.selected_players_data):
            export_list.append([
                i+1, p['LP2'], p['Zawodnik'], p['Kraj'], p['Wiek'], p['Płeć'],
                p['UM'], p['Forma'], p['L_UM'], p['L_F'], "Schtchutchinsk", 10, 10,
                p['C_UM'], p['UO_CALC'], p['FO_CALC'], p['UPO_FINAL'], p['FPO_FINAL'],
                int(p['CENA_WST']), int(p['CENA_FINAL'])
            ])

        pd.DataFrame(export_list, columns=self.calc_cols).to_csv(self.camps_path, index=False, sep=';', encoding='utf-8-sig')
        messagebox.showinfo("Sukces", f"Raport obozu zapisany:\n{self.camps_path}")

    def update_main_database(self):
        if not self.selected_players_data: return
        if not messagebox.askyesno("Zapis", f"Czy zaktualizować bazę główną i raport {self.camps_path}?"): return
        
        export_list = []
        for i, p in enumerate(self.selected_players_data):
            export_list.append([
                i+1, p['LP2'], p['Zawodnik'], p['Kraj'], p['Wiek'], p['Płeć'], 
                p['UM'], p['Forma'], p['L_UM'], p['L_F'], "Schtchutchinsk", 10, 10, 
                p['C_UM'], p['UO_CALC'], p['FO_CALC'], p['UPO_FINAL'], p['FPO_FINAL'], 
                int(p['CENA_WST']), int(p['CENA_FINAL'])
            ])
        
        pd.DataFrame(export_list, columns=self.calc_cols).to_csv(self.camps_path, index=False, sep=';', encoding='utf-8-sig')

        main_df = pd.read_csv(self.players_path)
        ups = {p['Zawodnik']: (p['UPO_FINAL'], p['FPO_FINAL']) for p in self.selected_players_data}
        for idx, row in main_df.iterrows():
            if row['Zawodnik'] in ups:
                main_df.at[idx, 'UM'], main_df.at[idx, 'Forma'] = ups[row['Zawodnik']]
        main_df.to_csv(self.players_path, index=False, encoding='utf-8-sig')
        messagebox.showinfo("Sukces", "Baza zaktualizowana.")

def build_gui(parent): return CampsModule(parent)

# ---------- STANDALONE ----------
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Obozy Szkoleniowe")
    root.geometry("1400x750")

    # Pasek z wyborem ścieżki do pliku zawodników
    top = ttk.Frame(root, padding=(6, 4))
    top.pack(fill=tk.X)

    ttk.Label(top, text="Plik zawodników:").pack(side=tk.LEFT)
    path_var = tk.StringVar(value=str(APP_DIR / "S51" / "Zawodnicy S51gpt.csv"))
    path_entry = ttk.Entry(top, textvariable=path_var, width=60)
    path_entry.pack(side=tk.LEFT, padx=(4, 2))

    app_ref = [None]

    def browse():
        p = filedialog.askopenfilename(
            title="Wybierz plik zawodników",
            filetypes=[("CSV", "*.csv"), ("Wszystkie", "*.*")]
        )
        if p:
            path_var.set(p)

    def reload_with_path():
        p = path_var.get().strip()
        if not p:
            return
        if app_ref[0]:
            app_ref[0].destroy()
        app = CampsModule(root)
        app.players_path = p
        # ustaw katalog S51 względem wybranego pliku
        S51 = str(Path(p).parent)
        fname = Path(p).stem  # np. "Zawodnicy S51gpt"
        import re
        m = re.search(r"S\d+", fname)
        season = m.group(0) if m else "S51"
        app.camps_path = str(Path(S51) / f"Obozy Szkoleniowe {season}.csv")
        app.costs_path = str(Path(S51) / f"Koszty Obozu {season}.csv")
        app.staff_m = app._smart_load_staff(f"Sztab M {season}.csv")
        app.staff_w = app._smart_load_staff(f"Sztab W {season}.csv")
        app._load_existing_camp_report()
        app.load_players_list()
        app.pack(fill=tk.BOTH, expand=True)
        app_ref[0] = app

    ttk.Button(top, text="…", command=browse).pack(side=tk.LEFT)
    ttk.Button(top, text="Wczytaj", command=reload_with_path).pack(side=tk.LEFT, padx=(6, 0))

    # Uruchom z domyślną ścieżką
    app = CampsModule(root)
    app.pack(fill=tk.BOTH, expand=True)
    app_ref[0] = app

    root.mainloop()
