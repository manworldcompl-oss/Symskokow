import sys
import os
import pandas as pd
from PySide6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                             QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                             QScrollArea, QTableWidget, QTableWidgetItem, QFrame)
from PySide6.QtGui import QPixmap, QIcon, QColor, QBrush, QFont
from PySide6.QtCore import Qt, QSize

class SportsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("System Statystyk Sportowych")
        self.resize(1200, 800)
        
        # Ścieżki
        self.flags_path = "./flags"
        self.data_path = "./Osiągnięcia"
        
        # 1. NAJPIERW inicjalizujemy cache i dane (to naprawi błąd)
        self.flag_cache = {} 
        self.nations = self.load_nations()
        
        # 2. DOPIERO POTEM budujemy interfejs
        self.main_tabs = QTabWidget()
        self.setCentralWidget(self.main_tabs)
        self.init_ui()

        self.setStyleSheet("""
            QMainWindow {
                background-color: white;
            }
            QScrollArea {
                border: none;
                background-color: white;
            }
            QWidget#ScrollContent {
                background-color: white;
            }
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                gridline-color: transparent; /* Ukrywamy siatkę */
                font-family: 'Segoe UI', Arial;
                color: #333;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                color: #5f6368;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #e8eaed;
                font-weight: bold;
                text-transform: uppercase;
                font-size: 10px;
            }
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                background: #f1f3f4;
                padding: 10px 20px;
                margin: 2px;
                border-radius: 5px;
            }
            QTabBar::tab:selected {
                background: #1a73e8;
                color: white;
                font-weight: bold;
            }
        """)

    def load_nations(self):
        # Szukamy w folderze głównym (tam gdzie jest plik .py)
        path = "ALL_NATIONS_NAT.csv" 
        
        if not os.path.exists(path):
            print(f"UWAGA: Nie znaleziono pliku {path} w folderze głównym!")
            return {}
            
        try:
            # Wczytujemy z pominięciem nagłówka NATION;NAT
            df = pd.read_csv(path, sep=';', header=None, skiprows=1, encoding='cp1250')
            
            # Mapujemy: Kolumna 1 (Skrót) -> Kolumna 0 (Pełna nazwa)
            # Dodajemy .upper(), żeby ignorować wielkość liter w skrótach
            nations_dict = {
                str(k).strip().upper(): str(v).strip() 
                for k, v in zip(df[1], df[0])
            }
            
            print(f"Załadowano {len(nations_dict)} narodowości.")
            return nations_dict
        except Exception as e:
            print(f"Błąd krytyczny ALL NATIONS: {e}")
            return {}

    def init_ui(self):
        # 5 Głównych Zakładek
        self.tab_cykle = QTabWidget()
        self.tab_turnieje = QTabWidget()
        self.tab_mistrzostwa = QTabWidget()
        self.tab_team = QWidget()
        self.tab_statystyki = QWidget()

        self.main_tabs.addTab(self.tab_cykle, "CYKLE")
        self.main_tabs.addTab(self.tab_turnieje, "TURNIEJE")
        self.main_tabs.addTab(self.tab_mistrzostwa, "MISTRZOSTWA")
        self.main_tabs.addTab(self.tab_team, "TEAM")
        self.main_tabs.addTab(self.tab_statystyki, "STATYSTYKI")

        self.setup_cykle()
        self.setup_mistrzostwa()
        self.setup_turnieje(self.tab_turnieje)
        self.setup_team()
        self.tab_coch_container = QTabWidget()
        
        # 4. PRZEKAZUJEMY ten kontener do funkcji (TUTAJ BYŁ BŁĄD)
        self.setup_coch(self.tab_coch_container)
        
        # 5. Dodajemy ten kontener jako jedną z zakładek w Mistrzostwach
        self.tab_mistrzostwa.addTab(self.tab_coch_container, "COCH")
        
        self.setup_statystyki(self.tab_statystyki)

    def setup_cykle(self):
        # Lista kategorii: (Nazwa widoczna, Prefix pliku)
        kategorie = [
            ("WORLD CUP", "WC"), ("CONTINENTAL CUP", "COC"), ("FIS CUP", "FC"),
            ("GRAND PRIX", "GP"), ("SUMMER COC", "SCOC"), ("JUNIOR CUP", "JC"),
            ("MINI CUP", "MC"), ("PICO CUP", "PC"), ("QUARTA CUP", "QC"),
            ("TOYOTA CUP", "TC"), ("AMAZON CUP", "AC"), ("BMW CUP", "BC"), ("DISNEY CUP", "DC")
        ]
        
        for nazwa, prefix in kategorie:
            scroller = QScrollArea()
            content = QWidget()
            content.setObjectName("ScrollContent") 
            layout = QVBoxLayout(content)
            
            # TWOJA KOLEJNOŚĆ: WC_IND_M.csv, WC_IND_W.csv, itd.
            pliki = [
                f"{prefix}_IND_M.csv", 
                f"{prefix}_IND_W.csv", 
                f"{prefix}_TEAM_M.csv", 
                f"{prefix}_TEAM_W.csv"
            ]
            
            # Wywołujemy renderowanie (układ 4 obok siebie)
            self.populate_championships(layout, pliki, "4x1")
            
            scroller.setWidget(content)
            scroller.setWidgetResizable(True)
            self.tab_cykle.addTab(scroller, nazwa)

    def setup_mistrzostwa(self):
        # Konfiguracja specyficznych podzakładek
        # Format: (Nazwa, Prefixy_Plików, Typ_Układu)
        podzakladki = [
            ("OG IND", ["OG_IND_M_LH", "OG_IND_M_NH", "OG_IND_W_LH", "OG_IND_W_NH"], "4x1"),
            ("OG TEAM", ["OG_TEAM_M_LH", "OG_TEAM_W_LH", "OG_TEAM_MIX_LH", 
                         "OG_TEAM_M_NH", "OG_TEAM_W_NH", "OG_TEAM_MIX_NH"], "3x2"),
            ("WCH IND", ["WCH_IND_M_LH", "WCH_IND_M_NH", "WCH_IND_W_LH", "WCH_IND_W_NH"], "4x1"),
            ("WCH TEAM", ["WCH_TEAM_M_LH", "WCH_TEAM_W_LH", "WCH_TEAM_MIX_LH", 
                         "WCH_TEAM_M_NH", "WCH_TEAM_W_NH", "WCH_TEAM_MIX_NH"], "3x2"),
            ("SFWC IND", ["SFWC_IND_M", "SFWC_IND_W"], "2x1"),
            ("SFWC TEAM", ["SFWC_TEAM_M", "SFWC_TEAM_W", "SFWC_TEAM_MIX"], "2x1"),
            ("JWC IND", ["JWC_IND_M", "JWC_IND_W"], "2x1"),
            ("JWC TEAM", ["JWC_TEAM_M", "JWC_TEAM_W", "JWC_TEAM_MIX"], "2x1"),
            ("YOG IND", ["YOG_IND_M", "YOG_IND_W"], "2x1"),
            ("YOG TEAM", ["YOG_TEAM_M", "YOG_TEAM_W", "YOG_TEAM_MIX"], "2x1"),
            ("UNI IND", ["UNI_IND_M", "UNI_IND_W"], "2x1"),
            ("UNI TEAM", ["UNI_TEAM_M", "UNI_TEAM_W", "UNI_TEAM_MIX"], "2x1"),
            ("NKIC", ["NKIC_IND_M", "NKIC_IND_W"], "2x1"),
            ("IST", ["IST_IND_M_LH", "IST_IND_M_NH", "IST_IND_W_LH", "IST_IND_W_NH"], "2x1"),
        ]

        for nazwa, pliki, uklad in podzakladki:
            scroller = QScrollArea()
            content = QWidget()
            layout = QVBoxLayout(content)
            
            # Przekazujemy pełne nazwy plików z rozszerzeniem .csv
            csv_files = [f"{p}.csv" for p in pliki]
            self.populate_championships(layout, csv_files, uklad)
            
            scroller.setWidget(content)
            scroller.setWidgetResizable(True)
            self.tab_mistrzostwa.addTab(scroller, nazwa)

    def setup_turnieje(self, target_tab_widget):
        grupy = [
            ("MĘŻCZYŹNI I", ["WCM_TCS.csv", "WCM_RAW_AIR.csv", "WCM_PLANICA7.csv", "WCM_WILLINGEN5.csv"], "4x1"),
            ("MĘŻCZYŹNI II", ["WCM_SKI_FLYING.csv", "WCM_NEW_TOURNAMENT.csv", "WCM_FINAL_TOURNAMENT.csv"], "3x1"),
            ("KOBIETY", ["WCW_RAW_AIR.csv", "WCW_BLUE_BIRD.csv", "WCW_SKI_FLYING.csv"], "3x1")
        ]

        for nazwa, pliki, uklad in grupy:
            scroller = QScrollArea()
            content = QWidget()
            content.setObjectName("ScrollContent")
            layout = QVBoxLayout(content)
            
            # Wypełnianie danymi
            self.populate_championships(layout, pliki, uklad)
            
            scroller.setWidget(content)
            scroller.setWidgetResizable(True)
            
            # Dodajemy podzakładkę do przekazanego widgetu
            target_tab_widget.addTab(scroller, nazwa)

    def setup_team(self):
        # 1. Tworzymy główny układ dla zakładki TEAM
        main_layout = QVBoxLayout(self.tab_team)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 2. Tworzymy ScrollArea, aby można było przewijać sezony
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setObjectName("MainScroll")
        
        content_widget = QWidget()
        content_widget.setObjectName("ScrollContent")
        layout = QVBoxLayout(content_widget)

        # 3. Lista plików do wczytania (4 obok siebie)
        pliki = [
            "FIXED_CC.csv", 
            "FIXED_MSC_M.csv", 
            "FIXED_MSC_W.csv", 
            "FIXED_NTC.csv"
        ]

        # 4. Wywołujemy naszą sprawdzoną funkcję renderującą
        # Używamy układu 4x1, aby tabele były w jednym rzędzie
        self.populate_championships(layout, pliki, "4x1")

        # 5. Składamy wszystko w całość
        scroller.setWidget(content_widget)
        main_layout.addWidget(scroller)

    def setup_statystyki(self, target_widget):
        main_layout = QVBoxLayout(target_widget)
        stat_tabs = QTabWidget()
        main_layout.addWidget(stat_tabs)

        # 4 Główne Podzakładki
        self.tab_stat_cykle = QTabWidget()
        self.tab_stat_turnieje = QTabWidget()
        self.tab_stat_mistrzostwa = QTabWidget()
        self.tab_stat_team = QWidget()

        stat_tabs.addTab(self.tab_stat_cykle, "CYKLE")
        stat_tabs.addTab(self.tab_stat_turnieje, "TURNIEJE")
        stat_tabs.addTab(self.tab_stat_mistrzostwa, "MISTRZOSTWA")
        stat_tabs.addTab(self.tab_stat_team, "TEAM")

        self.build_stat_cykle()
        self.build_stat_turnieje()
        self.build_stat_mistrzostwa()
        self.build_stat_team()

        self.tab_stat_cykle.setUsesScrollButtons(True)

    def get_medal_stats(self, filenames, mode="players"):
        all_data = []
        for f in filenames:
            path = os.path.join(self.data_path, f)
            if os.path.exists(path):
                try:
                    # Wymuszamy dtype=str, żeby kropki w "1." nie psuły odczytu
                    df = pd.read_csv(path, sep=';', header=None, encoding='cp1250', dtype=str).fillna("")
                    if not df.empty:
                        all_data.append(df)
                except: continue
        
        if not all_data:
            return pd.DataFrame()

        df_total = pd.concat(all_data)
        
        medal_map = {
            "1": "G", "2": "S", "3": "B", 
            "1.": "G", "2.": "S", "3.": "B",
            "W": "G", "F": "S", "SF": "B"
        }
        
        df_total['MedalType'] = df_total[1].astype(str).str.strip().map(medal_map)
        df_total = df_total[df_total['MedalType'].notna()]

        stats = {}
        for _, row in df_total.iterrows():
            # Liczba kolumn (bez dodanego MedalType)
            num_cols = len(row) - 1 

            if mode == "players":
                # Statystyki zawodników potrzebują min. 4 kolumn (Sezon;Msc;Zaw;Kraj)
                if num_cols >= 4:
                    key = str(row[2]).strip()
                    nat = str(row[3]).strip().upper()
                else: continue
            else:
                # TRYB KRAJÓW (TEAM)
                if num_cols >= 4:
                    # Jeśli plik ma 5+ kolumn (IND): kraj jest w [3] (np. POL)
                    # Jeśli plik ma 4 kolumny (TEAM): kraj/nazwa jest w [2] (np. Rosja lub RUS)
                    if num_cols >= 5:
                        raw_nat = str(row[3]).strip().upper()
                    else:
                        raw_nat = str(row[2]).strip().upper() # Dla plików TEAM
                    
                    # Szukamy pełnej nazwy w ALL NATIONS
                    key = self.nations.get(raw_nat, raw_nat)
                    # Jeśli raw_nat to pełna nazwa (np. Rosja), szukamy skrótu do flagi
                    # (To wymagałoby odwróconego słownika, ale na razie przypiszmy raw_nat)
                    nat = str(row[3]).strip().upper() if num_cols >= 4 else raw_nat
                else: continue

            if not key or key.lower() == "nan": continue

            if key not in stats:
                stats[key] = {"G": 0, "S": 0, "B": 0, "NAT": nat}
            
            stats[key][row['MedalType']] += 1

        result = []
        for name, m in stats.items():
            total = m["G"] + m["S"] + m["B"]
            if total > 0:
                result.append([m["G"], m["S"], m["B"], total, name, m["NAT"]])

        if not result: return pd.DataFrame()

        res_df = pd.DataFrame(result, columns=["G", "S", "B", "Total", "Name", "NAT"])
        res_df = res_df.sort_values(by=["G", "S", "B"], ascending=False).reset_index(drop=True)
        
        final_list = []
        for i, r in res_df.iterrows():
            medal_str = f"{r['G']}-{r['S']}-{r['B']} ({r['Total']})"
            final_list.append([0, i+1, r['Name'], r['NAT'], medal_str])
            
        return pd.DataFrame(final_list)
    
    def build_stat_cykle(self):
        # Definiujemy cykle i ich prefixy
        cykle = [
            ("WC", "WORLD CUP"), 
            ("COC", "CONT. CUP"), 
            ("FC", "FIS CUP"),
            ("GP", "GRAND PRIX"),
            ("SCOC", "SUMMER COC"),
            ("JC", "JUNIOR CUP"),
            ("MC", "MINI CUP"),
            ("PC", "PICO CUP"),
            ("QC", "QUARTA CUP"),
            ("TC", "TOYOTA CUP"),
            ("AC", "AMAZON CUP"),
            ("BC", "BMW CUP"),
            ("DC", "DISNEY CUP")
        ]
        
        for prefix, name in cykle:
            # Dla każdego cyklu robimy dwie zakładki: Mężczyźni i Kobiety
            for plec, suffix in [("M", "MEN"), ("W", "WOMEN")]:
                tab_name = f"{prefix} {plec}" # np. WC M
                
                container = QWidget()
                layout = QHBoxLayout(container)
                layout.setAlignment(Qt.AlignLeft)
                
                # --- TABELA 1: Medale IND zawodników ---
                # Plik: WC_IND_M.csv
                file_ind = [f"{prefix}_IND_{plec}.csv"]
                df_p = self.get_medal_stats(file_ind, mode="players")
                layout.addWidget(self.create_single_table("IND ZAWODNICY", df_p), alignment=Qt.AlignTop)
                
                # --- TABELA 2: Medale IND zsumowane na KRAJE ---
                # Ten sam plik, ale mode="countries"
                df_c = self.get_medal_stats(file_ind, mode="countries")
                layout.addWidget(self.create_single_table("KRAJE", df_c), alignment=Qt.AlignTop)
                
                # --- TABELA 3: Klasyfikacja Narodów (TEAM) ---
                # Plik: WC_TEAM_M.csv
                file_team = [f"{prefix}_TEAM_{plec}.csv"]
                df_t = self.get_medal_stats(file_team, mode="countries")
                layout.addWidget(self.create_single_table("NARODY (TEAM)", df_t), alignment=Qt.AlignTop)
                layout.addStretch()

                # Opakowanie w ScrollArea
                scroller = QScrollArea()
                scroller.setWidget(container)
                scroller.setWidgetResizable(True)
                
                # Dodanie do głównego widgetu statystyk cykli
                self.tab_stat_cykle.addTab(scroller, tab_name)

    def build_stat_mistrzostwa(self):
        # 1. OG i WCH (LH + NH)
        for m_type in ["OG", "WCH"]:
            sub_tabs = QTabWidget()
            self.tab_stat_mistrzostwa.addTab(sub_tabs, m_type)
            self.add_standard_stat_tabs(sub_tabs, m_type, has_lh_nh=True)

        # 2. SFWC, JWC, YOG, UNI (Bez LH/NH)
        for m_type in ["SFWC", "JWC", "YOG", "UNI"]:
            sub_tabs = QTabWidget()
            self.tab_stat_mistrzostwa.addTab(sub_tabs, m_type)
            self.add_standard_stat_tabs(sub_tabs, m_type, has_lh_nh=False)

        # 3. NKIC i IST
        for m_type in ["NKIC", "IST"]:
            sub_tabs = QTabWidget()
            self.tab_stat_mistrzostwa.addTab(sub_tabs, m_type)
            self.add_small_stat_tabs(sub_tabs, m_type)

        # 4. COCH (Kontynenty)
        coch_tabs = QTabWidget()
        self.tab_stat_mistrzostwa.addTab(coch_tabs, "COCH")
        kontynenty = ["EUROPE", "ASIA", "NORTH_AMERICA", "SOUTH_AMERICA", "AFRICA", "OCEANIA"]
        for kont in kontynenty:
            k_sub = QTabWidget()
            coch_tabs.addTab(k_sub, kont)
            self.add_standard_stat_tabs(k_sub, f"COCH_{kont}", has_lh_nh=False)

    def add_standard_stat_tabs(self, parent_tabs, prefix, has_lh_nh=False):
        # IND M
        p_m = [f"{prefix}_IND_M_LH.csv", f"{prefix}_IND_M_NH.csv"] if has_lh_nh else [f"{prefix}_IND_M.csv"]
        p_w = [f"{prefix}_IND_W_LH.csv", f"{prefix}_IND_W_NH.csv"] if has_lh_nh else [f"{prefix}_IND_W.csv"]
        p_tm = [f"{prefix}_TEAM_M_LH.csv", f"{prefix}_TEAM_M_NH.csv"] if has_lh_nh else [f"{prefix}_TEAM_M.csv"]
        p_tw = [f"{prefix}_TEAM_W_LH.csv", f"{prefix}_TEAM_W_NH.csv"] if has_lh_nh else [f"{prefix}_TEAM_W.csv"]
        p_tx = [f"{prefix}_TEAM_MIX_LH.csv", f"{prefix}_TEAM_MIX_NH.csv"] if has_lh_nh else [f"{prefix}_TEAM_MIX.csv"]

        sets = [
            (p_m, "IND M", ["ZAWODNICY", "KRAJE"], ["players", "countries"]),
            (p_w, "IND W", ["ZAWODNICY", "KRAJE"], ["players", "countries"]),
            ([p_tm, p_tw, p_tx], "TEAM", ["TEAM M", "TEAM W", "TEAM MIX"], ["countries", "countries", "countries"]),
            ([p_m+p_w, p_tm+p_tw+p_tx, p_m+p_w+p_tm+p_tw+p_tx], "ALL", ["ALL IND", "ALL TEAM", "TOTAL"], ["countries", "countries", "countries"])
        ]

        for paths, tab_label, titles, modes in sets:
            scroller = QScrollArea()
            scroller.setWidgetResizable(True)
            
            container = QWidget()
            container.setObjectName("ScrollContent")
            # QHBoxLayout dla tabel obok siebie
            layout = QHBoxLayout(container)
            layout.setAlignment(Qt.AlignTop | Qt.AlignLeft) # PRZYKLEJANIE DO GÓRY I LEWEJ
            
            # Dodajemy parametr alignment, aby każda tabela była wyrównana do góry niezależnie od innych
            if isinstance(paths[0], list):
                for path_list, title, mode in zip(paths, titles, modes):
                    layout.addWidget(
                        self.create_single_table(title, self.get_medal_stats(path_list, mode)),
                        alignment=Qt.AlignTop  # TO JEST KLUCZ
                    )
            else:
                for title, mode in zip(titles, modes):
                    layout.addWidget(
                        self.create_single_table(title, self.get_medal_stats(paths, mode)),
                        alignment=Qt.AlignTop  # TO JEST KLUCZ
                    )

            layout.addStretch() # WYPYCHANIE ELEMENTÓW DO GÓRY
            scroller.setWidget(container)
            parent_tabs.addTab(scroller, tab_label)

    def add_small_stat_tabs(self, parent_tabs, prefix):
        # Podobna logika dla NKIC i IST
        p_m = [f"{prefix}_IND_M_LH.csv", f"{prefix}_IND_M_NH.csv"] if prefix == "IST" else [f"{prefix}_IND_M.csv"]
        p_w = [f"{prefix}_IND_W_LH.csv", f"{prefix}_IND_W_NH.csv"] if prefix == "IST" else [f"{prefix}_IND_W.csv"]

        for paths, label in [(p_m, "IND M"), (p_w, "IND W"), (p_m + p_w, "ALL")]:
            scroller = QScrollArea()
            scroller.setWidgetResizable(True)
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

            if label == "ALL":
                layout.addWidget(self.create_single_table("TOTAL KRAJE", self.get_medal_stats(paths, "countries")), alignment=Qt.AlignTop)
            else:
                layout.addWidget(self.create_single_table("ZAWODNICY", self.get_medal_stats(paths, "players")), alignment=Qt.AlignTop)
                layout.addWidget(self.create_single_table("KRAJE", self.get_medal_stats(paths, "countries")), alignment=Qt.AlignTop)

            layout.addStretch()
            scroller.setWidget(container)
            parent_tabs.addTab(scroller, label)

    def build_stat_turnieje(self):
        # Lista turniejów
        turnieje = [
            ("TCS", ["WCM_TCS.csv"]),
            ("RAW AIR (M)", ["WCM_RAW_AIR.csv"]),
            ("PLANICA 7", ["WCM_PLANICA7.csv"]),
            ("WILLINGEN 5", ["WCM_WILLINGEN5.csv"]),
            ("LOTY (M)", ["WCM_SKI_FLYING.csv"]),
            ("NEW TOURN", ["WCM_NEW_TOURNAMENT.csv"]),
            ("FINAL TOURN", ["WCM_FINAL_TOURNAMENT.csv"]),
            ("RAW AIR (W)", ["WCW_RAW_AIR.csv"]),
            ("BLUE BIRD", ["WCW_BLUE_BIRD.csv"]),
            ("LOTY (W)", ["WCW_SKI_FLYING.csv"])
        ]

        for nazwa, pliki in turnieje:
            # 1. Tworzymy ScrollArea
            scroller = QScrollArea()
            scroller.setWidgetResizable(True)
            
            # 2. Tworzymy jeden wspólny kontener i layout
            container = QWidget()
            container.setObjectName("ScrollContent") # Dla stylu białego tła
            layout = QHBoxLayout(container)
            layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

            # 3. Pobieramy dane
            df_p = self.get_medal_stats(pliki, mode="players")
            df_c = self.get_medal_stats(pliki, mode="countries")

            # 4. Dodajemy tabele (tylko jeśli nie są puste)
            if not df_p.empty:
                layout.addWidget(self.create_single_table("ZAWODNICY", df_p), alignment=Qt.AlignTop)
            
            if not df_c.empty:
                layout.addWidget(self.create_single_table("KRAJE", df_c), alignment=Qt.AlignTop)

            # 5. Dodajemy stretch, żeby tabele były przyklejone do lewej
            layout.addStretch()
            
            # 6. Łączymy wszystko
            scroller.setWidget(container)
            self.tab_stat_turnieje.addTab(scroller, nazwa)

    def build_stat_team(self):
        # Czyścimy stary layout
        if self.tab_stat_team.layout() is not None:
            old_layout = self.tab_stat_team.layout()
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            QWidget().setLayout(old_layout)

        # Tworzymy główny layout
        layout_glowne = QVBoxLayout(self.tab_stat_team)
        layout_glowne.setContentsMargins(0,0,0,0)
        
        wewnetrzne_zakladki = QTabWidget()
        
        # --- ZAKŁADKA ZAWODY ---
        container_zawody = QWidget()
        lay_zawody = QHBoxLayout(container_zawody)
        lay_zawody.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        pliki = [
            ("FIXED_CC.csv", "CC"),
            ("FIXED_MSC_M.csv", "MSC M"),
            ("FIXED_MSC_W.csv", "MSC W"),
            ("FIXED_NTC.csv", "NTC")
        ]
        
        for plik, tytul in pliki:
            df = self.get_medal_stats([plik], mode="countries")
            if not df.empty:
                lay_zawody.addWidget(self.create_single_table(tytul, df), alignment=Qt.AlignTop)
        
        lay_zawody.addStretch()
        scroll_zawody = QScrollArea()
        scroll_zawody.setWidgetResizable(True)
        scroll_zawody.setWidget(container_zawody)
        wewnetrzne_zakladki.addTab(scroll_zawody, "ZAWODY")
        
        # --- ZAKŁADKA ALL ---
        container_all = QWidget()
        lay_all = QHBoxLayout(container_all)
        lay_all.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        wszystkie_pliki = [p[0] for p in pliki]
        df_all = self.get_medal_stats(wszystkie_pliki, mode="countries")
        
        if not df_all.empty:
            lay_all.addWidget(self.create_single_table("SUMA TEAM", df_all), alignment=Qt.AlignTop)
            
        lay_all.addStretch()
        scroll_all = QScrollArea()
        scroll_all.setWidgetResizable(True)
        scroll_all.setWidget(container_all)
        wewnetrzne_zakladki.addTab(scroll_all, "ALL")
        
        layout_glowne.addWidget(wewnetrzne_zakladki)

    def populate_championships(self, parent_layout, filenames, uklad):
        """Specjalne renderowanie dla Mistrzostw z różnymi układami siatki"""
        friendly_names = {
            "M_LH": "IND M LARGE HILL",
            "M_NH": "IND M NORMAL HILL",
            "W_LH": "IND W LARGE HILL",
            "W_NH": "IND W NORMAL HILL",
            "IND_M": "IND M",
            "IND_W": "IND W",
            "TEAM_M": "TEAM M",
            "TEAM_W": "TEAM W",
            "TEAM_MIX": "TEAM MIX",
            "TEAM_M_LH": "TEAM M LARGE HILL",
            "TEAM_W_LH": "TEAM W LARGE HILL",
            "TEAM_MIX_LH": "TEAM MIX LARGE HILL",
            "TEAM_M_NH": "TEAM M NORMAL HILL",
            "TEAM_W_NH": "TEAM W NORMAL HILL",
            "TEAM_MIX_NH": "TEAM MIX NORMAL HILL",

            "FIXED_CC": "CONTINENTAL CUP",
            "FIXED_MSC_M": "MSC MEN",
            "FIXED_MSC_W": "MSC WOMEN",
            "FIXED_NTC": "NATIONS CUP",

            "IND_M": "INDIVIDUAL MEN",
            "IND_W": "INDIVIDUAL WOMEN",
            "TEAM_M": "TEAM MEN",
            "TEAM_W": "TEAM WOMEN",

            "WCM_TCS": "TURNIEJ CZTERECH SKOCZNI",
            "WCM_RAW_AIR": "RAW AIR (M)",
            "WCM_PLANICA7": "PLANICA 7",
            "WCM_WILLINGEN5": "WILLINGEN 5",
            "WCM_SKI_FLYING": "LOTY NARCIARSKIE (M)",
            "WCM_NEW_TOURNAMENT": "NEW TOURNAMENT",
            "WCM_FINAL_TOURNAMENT": "FINAL TOURNAMENT",
            "WCW_RAW_AIR": "RAW AIR (W)",
            "WCW_BLUE_BIRD": "BLUE BIRD",
            "WCW_SKI_FLYING": "LOTY NARCIARSKIE (W)"
        }
        
        # 1. Wczytanie danych
        data_frames = []
        for f in filenames:
            path = os.path.join(self.data_path, f)
            if os.path.exists(path):
                df = pd.read_csv(path, sep=';', header=None, encoding='cp1250')
                data_frames.append(df)
            else:
                data_frames.append(pd.DataFrame()) # Pusty DF jeśli plik nie istnieje

        if not any(not df.empty for df in data_frames): return

        # 2. Pobranie unikalnych sezonów
        all_data = pd.concat([df for df in data_frames if not df.empty])
        sezony = sorted(all_data[0].unique(), reverse=False)

        for sezon in sezony:
            # Nagłówek sezonu na środku
            label_sezon = QLabel(f"SEZON {int(sezon)}")
            label_sezon.setAlignment(Qt.AlignCenter)
            label_sezon.setStyleSheet("""
                font-size: 22px; 
                font-weight: bold; 
                color: #202124; 
                border-top: 2px solid #f1f3f4;
            """)
            parent_layout.addWidget(label_sezon)
            
            # Grid dla tabel
            grid = QGridLayout()
            grid.setAlignment(Qt.AlignCenter) # Wyśrodkowanie całej grupy tabel
            grid.setSpacing(25) # Większy odstęp między tabelami (pionowy i poziomy)
            grid.setContentsMargins(20, 10, 20, 30) # Odstępy od krawędzi sekcji sezonu
            
            for idx, df in enumerate(data_frames):
                if df.empty: continue
                
                sezon_df = df[df[0] == sezon].reset_index(drop=True)
                if not sezon_df.empty:
                    # 1. Tworzymy kontener
                    table_container = QWidget()
                    v_box = QVBoxLayout(table_container)
                    v_box.setContentsMargins(0, 0, 0, 0)
                    v_box.setSpacing(5)
                    
                    # WYMUSZAMY WYŚRODKOWANIE W PIONOWYM UKŁADZIE
                    v_box.setAlignment(Qt.AlignCenter) 

                    # 2. Nazwa nad tabelą
                    current_file = filenames[idx].replace(".csv", "")
                    label_text = "DANE"
                    for key in friendly_names:
                        if current_file.endswith(key):
                            label_text = friendly_names[key]
                            break

                    lbl = QLabel(label_text)
                    lbl.setAlignment(Qt.AlignCenter)
                    lbl.setStyleSheet("font-weight: bold; color: #546e7a; font-size: 11px; text-transform: uppercase;")
                    
                    # 3. Tworzymy tabelę
                    table = self.create_single_table("", sezon_df)
                    
                    # 4. Dodajemy do VBoxa
                    v_box.addWidget(lbl)
                    v_box.addWidget(table)
                    
                    # 5. DODAJEMY DO GRIDU Z WYRÓWNANIEM DO ŚRODKA (Qt.AlignCenter)
                    if uklad == "4x1":
                        grid.addWidget(table_container, 0, idx, Qt.AlignCenter)
                    elif uklad == "3x2":
                        grid.addWidget(table_container, idx // 3, idx % 3, Qt.AlignCenter)
                    else:
                        grid.addWidget(table_container, 0, idx, Qt.AlignCenter)
                
            parent_layout.addLayout(grid)

    def create_single_table(self, title, dataframe):
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["POZ", "ZAWODNIK / KRAJ", "WYNIK"])
        
        row_count = len(dataframe)
        table.setRowCount(row_count)
        
        # --- USTAWIENIA WIDOKU ---
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False) 
        table.setAlternatingRowColors(True)
        table.setIconSize(QSize(25, 15))
        table.setFrameShape(QFrame.NoFrame) # Dodane dla lepszego dopasowania

        for i, row in dataframe.iterrows():
            num_cols = len(row)
            
            # 1. POZYCJA
            poz_raw = str(row.iloc[1])
            poz_clean = poz_raw.replace(".0", "").replace(".", "").strip()
            item_poz = QTableWidgetItem(poz_clean)
            item_poz.setTextAlignment(Qt.AlignCenter)
            
            # 2. ZAWODNIK / KRAJ + FLAGA
            if num_cols >= 5:
                # Plik IND: 2 to Zawodnik, 3 to Skrót kraju
                display_name = str(row.iloc[2]).strip()
                flag_code = str(row.iloc[3]).strip().lower()
                
                # Specjalna obsługa dla statystyk KRAJÓW, gdzie w kolumnie 2 jest już pełna nazwa
                # a w kolumnie 3 jest skrót (przekazany z get_medal_stats)
                if "nan" in display_name.lower(): display_name = ""
            elif num_cols == 4:
                # Plik TEAM lub STATS: 2 to Nazwa (Pełna), 3 to Skrót
                display_name = str(row.iloc[2]).strip()
                flag_code = str(row.iloc[3]).strip().lower()
            else:
                display_name = str(row.iloc[0]) if num_cols > 0 else ""
                flag_code = ""

            # Jeśli display_name to skrót, a mamy pełną nazwę w słowniku, podmień (na wszelki wypadek)
            if len(display_name) <= 3 and display_name.upper() in self.nations:
                display_name = self.nations[display_name.upper()]

            item_name = QTableWidgetItem(display_name)
            
            # LOGIKA FLAGI - zawsze na podstawie flag_code (skrótu)
            if flag_code and flag_code != "nan":
                if flag_code not in self.flag_cache:
                    flag_path = os.path.join(self.flags_path, f"{flag_code}.png")
                    if os.path.exists(flag_path):
                        self.flag_cache[flag_code] = QIcon(flag_path)
                    else:
                        self.flag_cache[flag_code] = None
                
                if self.flag_cache.get(flag_code):
                    item_name.setIcon(self.flag_cache[flag_code])
            
            # 3. WYNIK
            if num_cols >= 5:
                wynik_raw = str(row.iloc[4])
            elif num_cols == 4:
                wynik_raw = str(row.iloc[3])
            else:
                wynik_raw = ""
                
            wynik_clean = wynik_raw.replace(".0", "").replace("nan", "").strip()
            item_wynik = QTableWidgetItem(wynik_clean)
            item_wynik.setTextAlignment(Qt.AlignCenter)
            
            font_wynik = QFont()
            font_wynik.setBold(True)
            item_wynik.setFont(font_wynik)

            # --- KOLORY PODIUM ---
            bg_color = None
            poz_upper = poz_clean.upper()
            if poz_upper in ["1", "W"]: bg_color = QColor("#fff9c4")
            elif poz_upper in ["2", "F"]: bg_color = QColor("#f5f5f5")
            elif poz_upper in ["3", "SF"]: bg_color = QColor("#efebe9")

            for idx, item in enumerate([item_poz, item_name, item_wynik]):
                if bg_color:
                    item.setBackground(QBrush(bg_color))
                table.setItem(i, idx, item)

        # --- DOPASOWANIE ROZMIARÓW ---
        table.setColumnWidth(0, 25)
        table.setColumnWidth(1, 175)
        table.setColumnWidth(2, 80)
        
        row_h = 32
        header_h = 35
        table.verticalHeader().setDefaultSectionSize(row_h)
        table.horizontalHeader().setFixedHeight(header_h)
        
        total_h = header_h + (row_count * row_h) + 2
        table.setFixedSize(282, total_h)
        
        return table
    
    def populate_seasons(self, parent_layout, filenames):
        """Grupowanie danych po sezonie i tworzenie rzędów tabel"""
        all_data = []
        for f in filenames:
            path = os.path.join(self.data_path, f)
            if os.path.exists(path):
                df = pd.read_csv(path, sep=';', header=None, encoding='cp1250')
                all_data.append(df)
        
        if not all_data: return

        # Zakładamy, że kolumna 0 to sezon. Pobieramy unikalne sezony.
        combined = pd.concat(all_data)
        sezony = sorted(combined[0].unique(), reverse=True)

        for sezon in sezony:
            parent_layout.addWidget(QLabel(f"<h2>SEZON {sezon}</h2>"))
            row_layout = QHBoxLayout()
            
            for df in all_data:
                sezon_df = df[df[0] == sezon].reset_index(drop=True)
                if not sezon_df.empty:
                    table = self.create_single_table("", sezon_df)
                    row_layout.addWidget(table)
            
            parent_layout.addLayout(row_layout)

    def setup_coch(self, parent_tab_widget):
        """Generuje 12 zakładek dla Mistrzostw Kontynentalnych (COCH)"""
        kontynenty = ["EUROPE", "ASIA", "NORTH_AMERICA", "SOUTH_AMERICA", "AFRICA", "OCEANIA"]
        typy = ["IND", "TEAM"]

        for kontynent in kontynenty:
            for typ in typy:
                nazwa_zakladki = f"{kontynent} {typ}"
                scroller = QScrollArea()
                content = QWidget()
                layout = QVBoxLayout(content)

                # Generowanie nazw plików na podstawie schematu
                if typ == "IND":
                    # Przykład: COCH_EUROPE_IND_M.csv, COCH_EUROPE_IND_W.csv
                    pliki = [f"COCH_{kontynent}_IND_M.csv", f"COCH_{kontynent}_IND_W.csv"]
                    uklad = "2x1"
                else:
                    # Przykład: COCH_EUROPE_TEAM_M.csv, COCH_EUROPE_TEAM_W.csv, COCH_EUROPE_TEAM_MIX.csv
                    pliki = [f"COCH_{kontynent}_TEAM_M.csv", f"COCH_{kontynent}_TEAM_W.csv", f"COCH_{kontynent}_TEAM_MIX.csv"]
                    uklad = "3x1"

                # Wywołujemy stworzoną wcześniej funkcję do renderowania sezonów
                self.populate_championships(layout, pliki, uklad)

                scroller.setWidget(content)
                scroller.setWidgetResizable(True)
                parent_tab_widget.addTab(scroller, nazwa_zakladki)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SportsApp()
    window.show()
    sys.exit(app.exec())