from __future__ import annotations
import re
import sys
import os
import pandas as pd
from PySide6.QtWidgets import QInputDialog, QMessageBox, QLineEdit
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

# --- KONFIGURACJA ---
DEFAULT_CANDIDATES = [
    Path("./S51/Finanse S51.csv"),
    Path("Finanse S51.csv"),
]

def read_csv_loose(path: Path) -> pd.DataFrame:
    """Wczytuje CSV, obsługuje BOM i różne kodowania."""
    # utf-8-sig jest teraz priorytetem dla plików z GUI
    encodings = ("utf-8-sig", "utf-8", "cp1250", "latin1")
    
    for enc in encodings:
        try:
            # Próba ze średnikiem
            df = pd.read_csv(path, sep=';', engine="python", encoding=enc)
            
            if len(df.columns) <= 1:
                df = pd.read_csv(path, sep=None, engine="python", encoding=enc)
            
            if len(df.columns) > 1:
                # Czyszczenie nagłówków z BOM i spacji
                df.columns = [str(c).replace('\ufeff', '').strip() for c in df.columns]
                return df
        except Exception:
            continue
            
    return pd.read_csv(path, sep=";", engine="python", encoding="utf-8-sig")

def canonicalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    seen, uniq = {}, []
    # Dodajemy nawiasy wokół przypisania:
    for c in (cols := out.columns): 
        if c not in seen:
            seen[c] = 0; uniq.append(c)
        else:
            seen[c] += 1; uniq.append(f"{c}__{seen[c]}")
    out.columns = uniq
    return out

# --- MODELE WIDOKU ---
class DataFrameModel(QtCore.QAbstractTableModel):
    def __init__(self, df: pd.DataFrame, parent=None):
        super().__init__(parent)
        self._df = df

    def rowCount(self, p=QtCore.QModelIndex()): return len(self._df)
    def columnCount(self, p=QtCore.QModelIndex()): return len(self._df.columns)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        val = self._df.iat[index.row(), index.column()]

        # 1. ROLA WYŚWIETLANIA
        if role == QtCore.Qt.ItemDataRole.DisplayRole or role == QtCore.Qt.ItemDataRole.EditRole:
            return "" if pd.isna(val) else str(val)

        # 2. ROLA SORTOWANIA (Klucz do Twojego pytania)
        role_int = role.value if hasattr(role, 'value') else int(role)
        if role_int == 13:  # 13 = SortRole
            if pd.isna(val) or val == "":
                return 0
            
            # Jeśli to już jest liczba (int/float), zwróć ją bezpośrednio
            if isinstance(val, (int, float, complex)):
                return val
            
            # Jeśli to tekst (np. "1 200 €" lub "Polska")
            val_str = str(val).strip()
            
            # Spróbuj oczyścić tekst z formatowania finansowego, by sprawdzić czy to liczba
            # Usuwamy spacje, twarde spacje, symbole walut i zamieniamy przecinek na kropkę
            clean_val = val_str.replace('€', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
            
            try:
                # Próba konwersji na liczbę
                return float(clean_val)
            except ValueError:
                # Jeśli się nie udało (to prawdziwy tekst, np. nazwa kraju), sortuj małymi literami
                return val_str.lower()

        # 3. ROLA WYRÓWNANIA
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            if index.column() < 2:
                return QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
            else:
                return QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter

        return None
    
    def headerData(self, sect, orient, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole: return None
        return str(self._df.columns[sect]) if orient == QtCore.Qt.Horizontal else str(sect + 1)
    
class RegexFilterProxy(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setDynamicSortFilter(True)
    def setPattern(self, text):
        self.setFilterFixedString(text)

class GroupSeparatorDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, separator_indices, parent=None):
        super().__init__(parent)
        self.separator_indices = separator_indices

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        # Jeśli to kolumna kończąca grupę, rysujemy pionową linię na jej prawej krawędzi
        if index.column() in self.separator_indices:
            painter.save()
            # Ustawiamy kolor (np. ciemny szary) i grubość (2-3 piksele)
            pen = QtGui.QPen(QtGui.QColor(80, 80, 80), 2) 
            painter.setPen(pen)
            # Rysujemy od góry do dołu komórki dokładnie na prawym brzegu
            painter.drawLine(option.rect.topRight(), option.rect.bottomRight())
            painter.restore()

class FrozenTableView(QtWidgets.QTableView):
    def __init__(self, model):
        super().__init__()
        self.setModel(model)
        self.frozenTableView = QtWidgets.QTableView(self)
        self._init_frozen_view()
        
        # Synchronizacja przewijania i rozmiarów
        self.horizontalHeader().sectionResized.connect(self.updateSectionWidth)
        self.verticalHeader().sectionResized.connect(self.updateSectionHeight)
        self.frozenTableView.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self.verticalScrollBar().valueChanged.connect(self.frozenTableView.verticalScrollBar().setValue)

    def _init_frozen_view(self):
        self.frozenTableView.setModel(self.model())
        self.frozenTableView.setFocusPolicy(QtCore.Qt.NoFocus)
        self.frozenTableView.verticalHeader().hide()
        self.frozenTableView.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.frozenTableView.setStyleSheet("QTableView { border: none; background-color: #f0f0f0; selection-background-color: #999; }")
        self.frozenTableView.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.frozenTableView.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.frozenTableView.show()

        # Ukrywamy wszystko poza pierwszymi dwiema kolumnami (Reprezentacja i Kraj)
        for col in range(2, self.model().columnCount()):
            self.frozenTableView.setColumnHidden(col, True)

        self.viewport().stackUnder(self.frozenTableView)

        # Włączamy sortowanie na zamrożonym nagłówku
        frozen_header = self.frozenTableView.horizontalHeader()
        frozen_header.setSectionsClickable(True)
        frozen_header.setSortIndicatorShown(True)

        # Kliknięcie w zamrożony nagłówek → sortuje główną tabelę
        frozen_header.sectionClicked.connect(self._on_frozen_header_clicked)

        # Synchronizacja wskaźnika sortowania (strzałki) w obie strony
        self.horizontalHeader().sortIndicatorChanged.connect(self._sync_sort_indicator_to_frozen)
        frozen_header.sortIndicatorChanged.connect(self._sync_sort_indicator_to_main)

    def _on_frozen_header_clicked(self, logical_index):
        """Kliknięcie w nagłówek zamrożonej kolumny sortuje główną tabelę."""
        # Czytamy aktualny stan bezpośrednio z proxy (źródło prawdy)
        proxy = self.model()
        current_col = proxy.sortColumn()
        current_order = proxy.sortOrder()

        if current_col == logical_index:
            new_order = (QtCore.Qt.DescendingOrder
                         if current_order == QtCore.Qt.AscendingOrder
                         else QtCore.Qt.AscendingOrder)
        else:
            new_order = QtCore.Qt.AscendingOrder

        self.sortByColumn(logical_index, new_order)

    def _sync_sort_indicator_to_frozen(self, logical_index, order):
        """Gdy sortowanie zmieni się w głównej tabeli, aktualizuj strzałkę w zamrożonej."""
        frozen_header = self.frozenTableView.horizontalHeader()
        frozen_header.blockSignals(True)
        frozen_header.setSortIndicator(logical_index, order)
        frozen_header.blockSignals(False)

    def _sync_sort_indicator_to_main(self, logical_index, order):
        """Gdy sortowanie zmieni się w zamrożonej tabeli, aktualizuj strzałkę w głównej."""
        main_header = self.horizontalHeader()
        main_header.blockSignals(True)
        main_header.setSortIndicator(logical_index, order)
        main_header.blockSignals(False)

    def updateSectionWidth(self, logicalIndex, oldSize, newSize):
        if logicalIndex < 2:
            self.frozenTableView.setColumnWidth(logicalIndex, newSize)
            self.updateFrozenTableGeometry()

    def updateSectionHeight(self, logicalIndex, oldSize, newSize):
        self.frozenTableView.setRowHeight(logicalIndex, newSize)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateFrozenTableGeometry()

    def updateFrozenTableGeometry(self):
        # Ustala szerokość mrożonej części na podstawie pierwszych dwóch kolumn
        width = self.columnWidth(0) + self.columnWidth(1)
        header_height = self.horizontalHeader().height()
        self.frozenTableView.setGeometry(self.verticalHeader().width() + self.frameWidth(),
                                         self.frameWidth(), width, self.viewport().height() + header_height)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, initial_path: Path | None):
        super().__init__()
        self.setWindowTitle("Finanse S51 — Panel Sterowania")
        self.resize(1200, 800)
        
        self._last_dir = str(initial_path.parent) if initial_path else "."
        self._df = pd.DataFrame()

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central) # Powrót do układu pionowego

        # --- GÓRA: Ścieżka pliku ---
        top_bar = QtWidgets.QHBoxLayout()
        self.ed_path = QtWidgets.QLineEdit(str(initial_path) if initial_path else "")
        btn_browse = QtWidgets.QPushButton("…")
        btn_load = QtWidgets.QPushButton("Wczytaj")
        top_bar.addWidget(QtWidgets.QLabel("Plik:"))
        top_bar.addWidget(self.ed_path, stretch=1)
        top_bar.addWidget(btn_browse)
        top_bar.addWidget(btn_load)
        main_layout.addLayout(top_bar)

        # --- ŚRODEK: Filtr ---
        filter_bar = QtWidgets.QHBoxLayout()
        self.ed_filter = QtWidgets.QLineEdit()
        self.ed_filter.setPlaceholderText("Filtr...")
        btn_clear = QtWidgets.QPushButton("Wyczyść")
        filter_bar.addWidget(self.ed_filter, stretch=1)
        filter_bar.addWidget(btn_clear)
        main_layout.addLayout(filter_bar)

        # --- NOWOŚĆ: Panel 10 przycisków pod filtrem (Siatka 2x5) ---
        buttons_widget = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(buttons_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(5) # Mniejsze odstępy
        main_layout.addWidget(buttons_widget)
        
        self.custom_buttons = []
        for i in range(10):
            btn = QtWidgets.QPushButton(f"Przycisk {i+1}")
            btn.setMaximumHeight(30) # Niższe przyciski
            btn.setEnabled(False)
            # Rozmieszczenie: 2 rzędy po 5 przycisków
            row = i // 5
            col = i % 5
            self.grid_layout.addWidget(btn, row, col)
            self.custom_buttons.append(btn)

        # Konfiguracja Infrastruktury
        self.custom_buttons[0].setText("Infrastruktura")
        self.custom_buttons[0].setEnabled(True)
        self.custom_buttons[0].clicked.connect(self.run_infrastructure_update)
        # Konfiguracja Przycisku 2: Sponsorzy
        self.custom_buttons[1].setText("Sponsorzy")
        self.custom_buttons[1].setEnabled(True)
        self.custom_buttons[1].clicked.connect(self.run_sponsorship_update)
        # Konfiguracja Przycisku 3: Sztab
        self.custom_buttons[2].setText("Sztab")
        self.custom_buttons[2].setEnabled(True)
        self.custom_buttons[2].clicked.connect(self.run_staff_update)
        # Konfiguracja Przycisku 4: Skocznie
        self.custom_buttons[3].setText("Skocznie")
        self.custom_buttons[3].setEnabled(True)
        self.custom_buttons[3].clicked.connect(self.run_hills_update)
        # Konfiguracja Przycisku 5: Obozy
        self.custom_buttons[4].setText("Obozy")
        self.custom_buttons[4].setEnabled(True)
        self.custom_buttons[4].clicked.connect(self.run_camps_update)
        # Konfiguracja Przycisku 6: Juniorzy
        self.custom_buttons[5].setText("Juniorzy")
        self.custom_buttons[5].setEnabled(True)
        self.custom_buttons[5].clicked.connect(self.run_juniors_update)
        # Konfiguracja Przycisku 7: Konkursy
        self.custom_buttons[6].setText("Konkursy")
        self.custom_buttons[6].setEnabled(True)
        self.custom_buttons[6].clicked.connect(self.run_competitions_update)
        # Konfiguracja Przycisku 8: Nagrody
        self.custom_buttons[7].setText("Nagrody")
        self.custom_buttons[7].setEnabled(True)
        self.custom_buttons[7].clicked.connect(self.run_prizes_update)
        # Konfiguracja Przycisku 9: Budżet Końcowy
        self.custom_buttons[8].setText("Budżet i Nadwyżka")
        self.custom_buttons[8].setEnabled(True)
        self.custom_buttons[8].clicked.connect(self.run_budget_update)
        # Konfiguracja Przycisku 10: Nowy Sezon
        self.custom_buttons[9].setText("Nowy Sezon")
        self.custom_buttons[9].setEnabled(True)
        self.custom_buttons[9].clicked.connect(self.generuj_finanse_nowy_sezon)
        # --- DÓŁ: Tabela ---
        # 1. NAJPIERW TWÓRZ MODELE
        self.base_model = DataFrameModel(pd.DataFrame())
        self.proxy = RegexFilterProxy()
        self.proxy.setSourceModel(self.base_model)
        self.proxy.setSortRole(QtCore.Qt.ItemDataRole(13))
        self.proxy.setDynamicSortFilter(True)  # Dodaj tę linię, jeśli jej nie ma
        self.proxy.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive) # Dodaj to dla poprawnego sortowania A-Z

        self.view = FrozenTableView(self.proxy)
        self.view.setSortingEnabled(True)  # To musi być True
        self.view.horizontalHeader().setSortIndicator(-1, QtCore.Qt.AscendingOrder)
        self.view.setAlternatingRowColors(True)
        
        # Stylizacja (Twoje kolory i separatory)
        self.view.setStyleSheet("""
        QTableView {
            gridline-color: #d3d3d3;
        }
        QTableView::item {
            padding-left: 5px;
            padding-right: 5px; /* Daje trochę oddechu tekstowi przed linią separatora */
            }
    """)
        
        # 3. DODAJ DO UKŁADU
        main_layout.addWidget(self.view)

        # Sygnały
        btn_browse.clicked.connect(self._browse)
        btn_load.clicked.connect(self.load_now)
        btn_clear.clicked.connect(self._clear_filter)
        self.ed_filter.returnPressed.connect(self._apply_filter)

        if initial_path and initial_path.exists():
            QtCore.QTimer.singleShot(0, self.load_now)

    def run_infrastructure_update(self):
        """Aktualizuje Sz/Ek/In/Ed, liczy Infrastrukturę oraz Roz Infr (bez błędów typu)."""
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj plik główny!")
            return

        path_str = self.ed_path.text().strip()
        fin_path = Path(path_str)
        
        infra_path = fin_path.parent / fin_path.name.replace("Finanse", "Infrastruktura")
        expansion_path = fin_path.parent / fin_path.name.replace("Finanse", "Rozbudowa Infrastruktury")

        if not infra_path.exists():
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono pliku centrów:\n{infra_path.name}")
            return

        try:
            # --- 1. IMPORT I PRZYGOTOWANIE DANYCH ---
            original_columns = list(self._df.columns)
            df_infra = read_csv_loose(infra_path)
            
            col_infra = next((c for c in df_infra.columns if c.upper() == "KRAJ"), None)
            col_main = next((c for c in self._df.columns if c.upper() == "KRAJ"), None)

            mapping = {
                'Centrum Medyczne': 'Sz', 'Centrum Ekonomiczne': 'Ek',
                'Centrum Inżynieryjne': 'In', 'Centrum Edukacyjne': 'Ed',
                'Centrum Żywieniowe': 'Zy',
            }

            df_infra_mapped = df_infra.rename(columns={col_infra: col_main}).rename(columns=mapping)
            
            # Zamiana '-' na '0' i wymuszenie typu numerycznego dla danych z pliku zewnętrznego
            df_infra_mapped = df_infra_mapped.replace('-', '0')
            for col in mapping.values():
                if col in df_infra_mapped.columns:
                    df_infra_mapped[col] = pd.to_numeric(df_infra_mapped[col], errors='coerce').fillna(0).astype(int)

            # --- KLUCZOWA POPRAWKA: Wymuszenie typu w głównym DF ---
            for col in mapping.values():
                if col in self._df.columns:
                    self._df[col] = pd.to_numeric(self._df[col], errors='coerce').fillna(0).astype(int)

            # Aktualizacja (Merge/Update)
            self._df.set_index(col_main, inplace=True)
            df_infra_mapped.set_index(col_main, inplace=True)
            
            cols_to_update = [c for c in mapping.values() if c in self._df.columns and c in df_infra_mapped.columns]
            if cols_to_update:
                self._df.update(df_infra_mapped[cols_to_update])
            
            self._df.reset_index(inplace=True)
            self._df = self._df[original_columns]

            # --- 2. OBLICZENIA KOSZTÓW (Infrastruktura) ---
            def clean_money(series):
                return pd.to_numeric(series.astype(str).str.replace(r'[\s\xa0€]', '', regex=True), errors='coerce').fillna(0)

            # Konwersja do obliczeń
            sz = pd.to_numeric(self._df['Sz'], errors='coerce').fillna(0)
            ek = pd.to_numeric(self._df['Ek'], errors='coerce').fillna(0)
            in_val = pd.to_numeric(self._df['In'], errors='coerce').fillna(0)
            ed = pd.to_numeric(self._df['Ed'], errors='coerce').fillna(0)
            zy = pd.to_numeric(
                self._df['Zy'] if 'Zy' in self._df.columns else 0,
                errors='coerce'
            ).fillna(0)

            sp_glowny = clean_money(self._df['Sp. Główny'])
            sp_tech = clean_money(self._df['Sp. Techniczny'])

            cost_infra = (sz * 10000) + (ek * 10000) + (ek * 0.02 * (sp_glowny + sp_tech)) + (in_val * 20000) + (ed * 10000) + (zy * 10000)

            # --- 3. ROZBUDOWA ---
            cost_expansion_series = pd.Series(0, index=self._df[col_main])
            if expansion_path.exists():
                df_exp = read_csv_loose(expansion_path)
                df_exp['Cena'] = pd.to_numeric(df_exp['Cena'], errors='coerce').fillna(0)
                expansion_sums = df_exp.groupby('Kraj')['Cena'].sum()
                cost_expansion_series = self._df[col_main].map(expansion_sums).fillna(0)

            # --- 4. FORMATOWANIE I ZAPIS ---
            def format_exp(val):
                v = int(round(val))
                return f"-{v:,}".replace(",", " ") + " €" if v > 0 else "0 €"

            self._df['Infrastruktura'] = cost_infra.apply(format_exp)
            self._df['Roz Infr'] = cost_expansion_series.apply(format_exp)

            self._df.to_csv(fin_path, index=False, sep=';', encoding='utf-8-sig')
            self.load_now()
            QtWidgets.QMessageBox.information(self, "Sukces", "Zaktualizowano infrastrukturę bez błędów typów!")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Szczegóły: {str(e)}")

    def run_sponsorship_update(self):
        """Aktualizuje kolumny Sp. Główny i Sp. Techniczny wg wzorów."""
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj plik!")
            return

        try:
            # Tworzymy roboczą kopię danych, aby ułatwić obliczenia numeryczne
            df = self._df.copy()

            # Konwersja kolumn wejściowych na liczby (obsługa błędów i myślników)
            for col in ['M*', 'K*', 'Ek']:
                if col in df.columns:
                    # Zamieniamy wszystko co nie jest liczbą na 0 na potrzeby obliczeń
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                else:
                    QtWidgets.QMessageBox.critical(self, "Błąd", f"Brak kolumny: {col}")
                    return

            # --- OBLICZENIA ---
            # Średnia z M* i K*
            avg_mk = (df['M*'] + df['K*']) / 2
            # Mnożnik ekonomii (np. Ek=2 -> 1.2)
            ek_factor = 1 + (df['Ek'] * 0.1)

            # Sponsor Główny: ((średnia - 1) * 35000 + 300000) * mnożnik_Ek
            val_glowny = ((avg_mk - 1) * 35000 + 300000) * ek_factor
            
            # Sponsor Techniczny: 20000 * średnia * mnożnik_Ek
            val_techniczny = 20000 * avg_mk * ek_factor

            # --- FORMATOWANIE I ZAPIS ---
            def format_fin(val):
                """Formatuje liczbę na styl '1 234 567 €'"""
                val = int(round(val))
                return f"{val:,}".replace(",", " ") + " €"

            self._df['Sp. Główny'] = val_glowny.apply(format_fin)
            self._df['Sp. Techniczny'] = val_techniczny.apply(format_fin)

            # Zapis do pliku CSV
            path_str = self.ed_path.text().strip()
            self._df.to_csv(path_str, index=False, sep=';', encoding='utf-8-sig')
            
            # Odświeżenie widoku w programie
            self.load_now()
            QtWidgets.QMessageBox.information(self, "Sukces", "Przychody od sponsorów zostały przeliczone!")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd Obliczeń", f"Szczegóły: {str(e)}")

    def run_staff_update(self):
        """Sumuje wydatki na sztab i wylicza Sztab Ek jako % kosztów (1 pkt Ek = 10%)."""
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj plik główny!")
            return

        path_str = self.ed_path.text().strip()
        fin_path = Path(path_str)
        
        staff_m_name = fin_path.name.replace("Finanse", "Sztab M")
        staff_w_name = fin_path.name.replace("Finanse", "Sztab W")
        staff_m_path = fin_path.parent / staff_m_name
        staff_w_path = fin_path.parent / staff_w_name

        if not staff_m_path.exists() or not staff_w_path.exists():
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Brak plików sztabu w folderze!")
            return

        try:
            # 1. Funkcja pomocnicza do czytania kosztów
            def get_staff_costs(path):
                df_s = read_csv_loose(path)
                # Usuwamy spacje i inne białe znaki z kolumny Money
                df_s['Money'] = df_s['Money'].astype(str).str.replace(r'[\s\xa0]', '', regex=True)
                df_s['Money'] = pd.to_numeric(df_s['Money'], errors='coerce').fillna(0)
                return df_s.groupby('NAT')['Money'].sum()

            # 2. Obliczenia sumaryczne kosztów z obu plików
            total_staff_series = get_staff_costs(staff_m_path).add(get_staff_costs(staff_w_path), fill_value=0)

            # 3. Pobieranie danych do głównego DataFrame
            col_main = next((c for c in self._df.columns if c.upper() == "KRAJ"), None)
            
            # Pobieramy czyste wartości liczbowe
            raw_staff = self._df[col_main].map(total_staff_series).fillna(0)
            # Konwersja Ek na liczbę (1 pkt = 0.1)
            raw_ek = pd.to_numeric(self._df['Ek'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

            # --- OBLICZENIA ---
            # Sztab: Pełny koszt (jako wydatek)
            # Sztab Ek: Koszt * (Poziom Ek * 10%)
            raw_staff_ek = raw_staff * (raw_ek * 0.1)

            # --- FORMATOWANIE ---
            def format_exp(val):
                """Formatowanie wydatków (z minusem: -100 000 €)"""
                v = int(round(val))
                return f"-{v:,}".replace(",", " ") + " €" if v > 0 else "0 €"

            def format_val(val):
                """Formatowanie wartości (bez minusa: 20 000 €)"""
                v = int(round(val))
                return f"{v:,}".replace(",", " ") + " €" if v != 0 else "0 €"

            # Aktualizacja kolumn
            self._df['Sztab'] = raw_staff.apply(format_exp)
            self._df['Sztab Ek'] = raw_staff_ek.apply(format_val)

            # 4. Zapis i odświeżenie
            self._df.to_csv(fin_path, index=False, sep=';', encoding='utf-8-sig')
            self.load_now()
            QtWidgets.QMessageBox.information(self, "Sukces", "Zaktualizowano koszty sztabu (Sztab Ek = 10% za pkt Ek).")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Szczegóły: {str(e)}")

    def run_hills_update(self):
        """Aktualizuje kolumny Skocznie, Skocznie In oraz Roz Skoczni."""
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj plik główny!")
            return

        path_str = self.ed_path.text().strip()
        fin_path = Path(path_str)
        
        # Dynamiczne nazwy plików
        hills_name = fin_path.name.replace("Finanse", "Utrzymanie Skoczni")
        hills_path = fin_path.parent / hills_name

        # Szukamy pliku rozbudowy pod kilkoma możliwymi nazwami
        season = fin_path.stem.split()[-1]  # np. "S51"
        expansion_candidates = [
            fin_path.parent / fin_path.name.replace("Finanse", "Rozbudowa"),
            fin_path.parent / f"Koszty_rozbudowy_skoczni_{season}.csv",
            fin_path.parent / f"Rozbudowa Skoczni {season}.csv",
        ]
        expansion_path = next((p for p in expansion_candidates if p.exists()), expansion_candidates[0])

        if not hills_path.exists():
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono pliku skoczni:\n{hills_name}")
            return

        try:
            # 1. Odczyt i przygotowanie kosztów utrzymania (Skocznie)
            df_h = read_csv_loose(hills_path)
            df_h['Suma'] = df_h['Suma'].astype(str).str.replace(r'[\s\xa0€]', '', regex=True)
            df_h['Suma'] = pd.to_numeric(df_h['Suma'], errors='coerce').fillna(0)
            hills_map = df_h.set_index('Kraj')['Suma']

            # 2. Odczyt i przygotowanie kosztów rozbudowy (Roz Skoczni)
            cost_expansion_series = pd.Series(0, index=self._df.index)
            if expansion_path.exists():
                df_exp = read_csv_loose(expansion_path)
                # Obsługujemy kolumnę 'Cena' lub 'Suma'
                exp_col = next((c for c in df_exp.columns if c in ('Cena', 'Suma')), None)
                if exp_col is None:
                    raise KeyError(f"Brak kolumny 'Cena' lub 'Suma' w pliku {expansion_path.name}")
                df_exp[exp_col] = df_exp[exp_col].astype(str).str.replace(r'[\s\xa0]', '', regex=True)
                df_exp[exp_col] = pd.to_numeric(df_exp[exp_col], errors='coerce').fillna(0)
                # Sumujemy wartości grupując po kolumnie Kraj
                expansion_sums = df_exp.groupby('Kraj')[exp_col].sum()
            else:
                expansion_sums = pd.Series(dtype=float)

            # 3. Pobieranie danych z głównego DataFrame
            col_main = next((c for c in self._df.columns if c.upper() == "KRAJ"), None)
            
            raw_hills = self._df[col_main].map(hills_map).fillna(0)
            raw_in = pd.to_numeric(self._df['In'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            raw_expansion = self._df[col_main].map(expansion_sums).fillna(0)

            # --- OBLICZENIA ---
            # Skocznie: Koszt utrzymania (ujemny)
            # Skocznie In: Zniżka (In * 4%)
            # Roz Skoczni: Suma z pliku Rozbudowa (ujemny)
            raw_hills_in = raw_hills * (raw_in * 0.04)

            # --- FORMATOWANIE ---
            def format_exp(val):
                v = int(round(val))
                return f"-{v:,}".replace(",", " ") + " €" if v > 0 else "0 €"

            def format_val(val):
                v = int(round(val))
                return f"{v:,}".replace(",", " ") + " €" if v != 0 else "0 €"

            # Aktualizacja kolumn
            self._df['Skocznie'] = raw_hills.apply(format_exp)
            self._df['Skocznie In'] = raw_hills_in.apply(format_val)
            self._df['Roz Skoczni'] = raw_expansion.apply(format_exp)

            # 4. Zapis i odświeżenie
            self._df.to_csv(fin_path, index=False, sep=';', encoding='utf-8-sig')
            self.load_now()
            QtWidgets.QMessageBox.information(self, "Sukces", "Zaktualizowano Skocznie oraz Roz Skoczni!")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Szczegóły: {str(e)}")

    def run_camps_update(self):
        """Aktualizuje kolumnę Obozy Sz. na podstawie pliku Koszty Obozu [Sezon].csv."""
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj plik główny!")
            return

        path_str = self.ed_path.text().strip()
        fin_path = Path(path_str)
        
        # Dynamiczne tworzenie nazwy pliku (np. Finanse S51 -> Koszty Obozu S51)
        camps_name = fin_path.name.replace("Finanse", "Koszty Obozu")
        camps_path = fin_path.parent / camps_name

        if not camps_path.exists():
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono pliku obozów:\n{camps_name}")
            return

        try:
            # 1. Odczyt danych o obozach
            # Używamy read_csv_loose, ale musimy uważać na separator (często w CSV jest przecinek)
            df_c = read_csv_loose(camps_path)
            
            # Identyfikacja kolumn (Kraj i Koszt)
            col_country_c = next((c for c in df_c.columns if c.upper() == "KRAJ"), None)
            col_cost = next((c for c in df_c.columns if c.upper() == "KOSZT"), None)

            if not col_country_c or not col_cost:
                QtWidgets.QMessageBox.critical(self, "Błąd", f"Plik {camps_name} nie posiada wymaganych kolumn (Kraj, Koszt)!")
                return

            # Czyścimy dane (usuwamy spacje, symbole walut)
            df_c[col_cost] = df_c[col_cost].astype(str).str.replace(r'[\s\xa0€]', '', regex=True)
            df_c[col_cost] = pd.to_numeric(df_c[col_cost], errors='coerce').fillna(0)
            
            # Tworzymy mapę {KRAJ: KOSZT}
            camps_map = df_c.groupby(col_country_c)[col_cost].sum()

            # 2. Pobieranie danych z głównego DataFrame
            col_main = next((c for c in self._df.columns if c.upper() == "KRAJ"), None)
            raw_camps = self._df[col_main].map(camps_map).fillna(0)

            # --- FORMATOWANIE ---
            def format_exp(val):
                v = int(round(val))
                return f"-{v:,}".replace(",", " ") + " €" if v > 0 else "0 €"

            # 3. Aktualizacja kolumn w głównym pliku
            self._df['Obozy Sz.'] = raw_camps.apply(format_exp)
            self._df['Obozy Lecz.'] = "0 €"  # Zgodnie z prośbą ustawiamy na sztywno 0

            # 4. Zapis i odświeżenie
            self._df.to_csv(fin_path, index=False, sep=';', encoding='utf-8-sig')
            self.load_now()
            QtWidgets.QMessageBox.information(self, "Sukces", "Zaktualizowano koszty obozów szkoleniowych!")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Szczegóły: {str(e)}")

    def run_juniors_update(self):
        """Aktualizuje kolumnę Juniorzy na podstawie pliku Koszty Juniorów [Sezon].csv."""
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj plik główny!")
            return

        path_str = self.ed_path.text().strip()
        fin_path = Path(path_str)
        
        # Dynamiczne tworzenie nazwy pliku (Finanse S51 -> Koszty Juniorów S51)
        juniors_name = fin_path.name.replace("Finanse", "Koszty Juniorów")
        juniors_path = fin_path.parent / juniors_name

        if not juniors_path.exists():
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono pliku:\n{juniors_name}")
            return

        try:
            # 1. Odczyt danych o juniorach
            df_j = read_csv_loose(juniors_path)
            
            # Sprawdzamy kolumny w pliku juniorów
            col_cost = 'Suma Kosztów'
            col_country_j = 'Kraj'
            
            if col_cost not in df_j.columns or col_country_j not in df_j.columns:
                QtWidgets.QMessageBox.critical(self, "Błąd", f"Plik {juniors_name} nie posiada wymaganych kolumn (Kraj, Suma Kosztów)!")
                return

            # Czyścimy dane (usuwamy spacje i zamieniamy na liczby)
            df_j[col_cost] = df_j[col_cost].astype(str).str.replace(r'[\s\xa0€]', '', regex=True)
            df_j[col_cost] = pd.to_numeric(df_j[col_cost], errors='coerce').fillna(0)
            
            # Mapujemy {KRAJ: SUMA} (na wypadek gdyby kraj wystąpił kilka razy, robimy sumę)
            juniors_map = df_j.groupby(col_country_j)[col_cost].sum()

            # 2. Pobieranie danych z głównego DataFrame
            col_main = next((c for c in self._df.columns if c.upper() == "KRAJ"), None)
            
            # Mapujemy wartości na główną tabelę
            raw_juniors = self._df[col_main].map(juniors_map).fillna(0)

            # --- FORMATOWANIE ---
            def format_exp(val):
                v = int(round(val))
                return f"-{v:,}".replace(",", " ") + " €" if v > 0 else "0 €"

            # Aktualizacja kolumny 'Juniorzy'
            self._df['Juniorzy'] = raw_juniors.apply(format_exp)

            # 3. Zapis i odświeżenie
            self._df.to_csv(fin_path, index=False, sep=';', encoding='utf-8-sig')
            self.load_now()
            QtWidgets.QMessageBox.information(self, "Sukces", "Zaktualizowano koszty juniorów!")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Szczegóły: {str(e)}")
    
    def run_competitions_update(self):
        """Aktualizuje kolumnę Konkursy na podstawie pliku Zysk Konkursy [Sezon].csv."""
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj arkusz główny!")
            return

        fin_path = Path(self.ed_path.text().strip())
        # Szukamy pliku: Zysk Konkursy S51.csv
        zyskk_name = fin_path.name.replace("Finanse", "Zysk Konkursy")
        zyskk_path = fin_path.parent / zyskk_name

        if not zyskk_path.exists():
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono pliku:\n{zyskk_name}")
            return

        try:
            df_zyskk = read_csv_loose(zyskk_path)
            
            # POPRAWKA: Szukamy NAT lub Kraj
            col_country = next((c for c in df_zyskk.columns if c.upper() in ["KRAJ", "NAT"]), None)
            col_cost = next((c for c in df_zyskk.columns if "ZYSK FINALNY" in c.upper()), None)
            
            if not col_cost or not col_country:
                QtWidgets.QMessageBox.critical(self, "Błąd", "Nie znaleziono kolumn NAT/Kraj lub Zysk Finalny!")
                return

            # Czyszczenie liczb ze spacji
            df_zyskk[col_cost] = df_zyskk[col_cost].astype(str).str.replace(r'[\s\xa0€]', '', regex=True)
            df_zyskk[col_cost] = pd.to_numeric(df_zyskk[col_cost], errors='coerce').fillna(0)
            
            zyskk_map = df_zyskk.groupby(col_country)[col_cost].sum()

            col_main = next((c for c in self._df.columns if c.upper() == "KRAJ"), None)
            raw_vals = self._df[col_main].map(zyskk_map).fillna(0)

            # Formatowanie: Zysk jest dodatni (bez minusa)
            self._df['Konkursy'] = raw_vals.apply(lambda v: f"{int(round(v)):,}".replace(",", " ") + " €")

            self._df.to_csv(fin_path, index=False, sep=';', encoding='utf-8-sig')
            self.load_now()
            QtWidgets.QMessageBox.information(self, "Sukces", "Zaktualizowano zyski z konkursów!")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Szczegóły: {str(e)}")

    def run_prizes_update(self):
        """Aktualizuje kolumnę Nagrody na podstawie pliku Nagrody S51.csv."""
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj arkusz główny!")
            return

        path_str = self.ed_path.text().strip()
        fin_path = Path(path_str)
        
        # Budujemy ścieżkę do pliku Nagrody S51.csv
        prizes_name = fin_path.name.replace("Finanse", "Nagrody")
        prizes_path = fin_path.parent / prizes_name

        if not prizes_path.exists():
            QtWidgets.QMessageBox.warning(self, "Błąd", f"Nie znaleziono pliku:\n{prizes_name}")
            return

        try:
            # 1. Wczytujemy dane z pliku nagród
            df_p = read_csv_loose(prizes_path)
            
            # 2. DEFINICJA KLUCZY (Zgodnie z Twoim opisem):
            # Finanse: 'KRAJ' (skrót), Nagrody: 'NAT' (skrót)
            col_main_key = "KRAJ"
            col_prizes_key = "NAT"
            col_prizes_val = "SUMA"

            # Sprawdzenie, czy kolumny istnieją
            if col_main_key not in self._df.columns:
                QtWidgets.QMessageBox.critical(self, "Błąd", f"W arkuszu głównym nie ma kolumny '{col_main_key}'!")
                return
            
            if col_prizes_key not in df_p.columns or col_prizes_val not in df_p.columns:
                QtWidgets.QMessageBox.critical(self, "Błąd", f"W pliku nagród brakuje kolumn: {col_prizes_key} lub {col_prizes_val}")
                return

            # 3. Czyszczenie danych liczbowych (zamiana 5000.0 na 5000)
            df_p[col_prizes_val] = pd.to_numeric(
                df_p[col_prizes_val].astype(str).str.replace(r'[^\d.]', '', regex=True), 
                errors='coerce'
            ).fillna(0)

            # 4. Tworzenie mapy połączeń po skrótach (np. {'SLO': 5351500.0})
            prizes_dict = df_p.set_index(col_prizes_key)[col_prizes_val].to_dict()

            # 5. Aktualizacja głównego DataFrame
            # Mapujemy wartości z Nagród do kolumny Nagrody w Finansach używając skrótu KRAJ
            raw_prizes = self._df[col_main_key].map(prizes_dict).fillna(0)

            # Formatowanie waluty: 1 000 000 €
            def format_currency(val):
                v = int(float(val))
                return f"{v:,}".replace(",", " ") + " €" if v > 0 else "0 €"

            self._df['Nagrody'] = raw_prizes.apply(format_currency)

            # 6. Zapis i odświeżenie
            self._df.to_csv(fin_path, index=False, sep=';', encoding='utf-8-sig')
            self.load_now()
            
            QtWidgets.QMessageBox.information(self, "Sukces", "Nagrody zaktualizowane (powiązanie po skrótach KRAJ/NAT).")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Szczegóły: {str(e)}")

    def run_budget_update(self):
        """
        1. Pobiera gwiazdki M*.1 i K*.1.
        2. Liczy BUDŻET KOŃCOWY i Nadwyżkę.
        3. Liczy Budżet startowy (na nowy sezon) wg wzoru.
        """
        if self._df.empty:
            QtWidgets.QMessageBox.warning(self, "Błąd", "Najpierw wczytaj plik finansów!")
            return

        try:
            # --- KROK 0: DYNAMICZNE WYKRYWANIE SEZONU ---
            current_path = Path(self.ed_path.text())
            current_filename = current_path.name  
            match = re.search(r'S(\d+)', current_filename)
            s_val = f"S{match.group(1)}" if match else "S51"

            base_dir = Path(f"./{s_val}")
            file_m = base_dir / f"Ranking FIS M {s_val}.csv"
            file_w = base_dir / f"Ranking FIS W {s_val}.csv"

            # --- KROK 1: POBIERANIE GWIAZDEK (M*.1 i K*.1) ---
            def get_stars_dict(file_path):
                if not file_path.exists():
                    return {}
                rdf = pd.read_csv(file_path, sep=';', encoding='utf-8-sig')
                # Czyścimy nagłówki z białych znaków
                rdf.columns = [str(c).strip() for c in rdf.columns]
                if 'NAT' in rdf.columns and '*' in rdf.columns:
                    return dict(zip(rdf['NAT'], rdf['*']))
                return {}

            stars_m = get_stars_dict(file_m)
            stars_w = get_stars_dict(file_w)

            # Aktualizacja gwiazdek na przyszły sezon
            if 'KRAJ' in self._df.columns:
                self._df['M*.1'] = self._df['KRAJ'].map(stars_m).fillna(0).astype(int)
                self._df['K*.1'] = self._df['KRAJ'].map(stars_w).fillna(0).astype(int)

            # --- KROK 2: OBLICZENIA FINANSOWE (BUDŻET KOŃCOWY i NADWYŻKA) ---
            cols_to_sum = [
                'BUDŻET STARTOWY', 'Pożyczka', 'Sp. Główny', 'Sp. Techniczny',
                'Konkursy', 'Nagrody', 'Sztab', 'Sztab Ek', 'Skocznie',
                'Skocznie In', 'Roz Skoczni', 'Infrastruktura', 'Roz Infr',
                'Obozy Sz.', 'Obozy Lecz.', 'Juniorzy'
            ]

            def clean_to_num(series):
                if series is None: return 0
                s = series.astype(str).str.replace(r'[^\d\.-]', '', regex=True)
                return pd.to_numeric(s, errors='coerce').fillna(0)

            # Suma liczbowa budżetu końcowego
            total_budget_val = pd.Series(0.0, index=self._df.index)
            for col in cols_to_sum:
                if col in self._df.columns:
                    total_budget_val += clean_to_num(self._df[col])

            # Nadwyżka (25% z dodatniego, 100% z ujemnego)
            surplus_val = total_budget_val.apply(lambda x: x * 0.25 if x > 0 else x)

            # --- KROK 3: OBLICZENIE NOWEJ KOLUMNY 'Budżet startowy' ---
            # Wzór: BUDŻET KOŃCOWY + (750000 + (M*.1 + K*.1) / 2 * 200000)
            stars_avg = (self._df['M*.1'] + self._df['K*.1']) / 2
            next_season_start_val = total_budget_val + (750000 + (stars_avg * 200000))

            # --- KROK 4: FORMATOWANIE I ZAPIS ---
            def format_fin(val):
                v = int(round(val))
                if v < 0:
                    return f"-{abs(v):,}".replace(",", " ") + " €"
                return f"{v:,}".replace(",", " ") + " €"

            self._df['BUDŻET KOŃCOWY'] = total_budget_val.apply(format_fin)
            self._df['Nadwyżka'] = surplus_val.apply(format_fin)
            self._df['Budżet startowy'] = next_season_start_val.apply(format_fin)

            # Zapis do pliku CSV
            self._df.to_csv(str(current_path), index=False, sep=';', encoding='utf-8-sig')
            self.load_now()
            
            QtWidgets.QMessageBox.information(self, "Sukces", 
                f"Zaktualizowano dane dla sezonu {s_val}!\n\n"
                "1. Pobrano nowe gwiazdki (M*.1 i K*.1).\n"
                "2. Przeliczono Budżet Końcowy i Nadwyżkę.\n"
                "3. Wyliczono Budżet startowy na kolejny sezon.")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd", f"Szczegóły: {str(e)}")

    def generuj_finanse_nowy_sezon(self, *args):
        nowy_sezon, ok = QInputDialog.getText(
            None, "Nowy Sezon", "Podaj nazwę nowego sezonu (np. S51):",
            QLineEdit.Normal, ""
        )
        
        if not ok or not nowy_sezon.strip():
            return 

        try:
            # 1. Obliczanie ścieżki do poprzedniego sezonu (np. S51)
            import re
            liczby = re.findall(r'\d+', nowy_sezon)
            if not liczby:
                QMessageBox.warning(self, "Błąd", "Nazwa sezonu musi zawierać numer (np. S51)")
                return
            
            numer_nowego = int(liczby[0])
            numer_starego = numer_nowego - 1
            stary_sezon = f"S{numer_starego}"

            # Szukamy źródła: ./S51/Finanse S51.csv
            sciezka_stara = os.path.join(stary_sezon, f"Finanse {stary_sezon}.csv")
            
            # Zabezpieczenie dla startu projektu (jeśli plik jest w folderze głównym)
            if not os.path.exists(sciezka_stara) and numer_starego == 38:
                 sciezka_stara = "Finanse S51.csv"

            if not os.path.exists(sciezka_stara):
                QMessageBox.critical(self, "Błąd", f"Nie znaleziono pliku: {sciezka_stara}")
                return

            # 2. Tworzenie folderu dla nowego sezonu
            if not os.path.exists(nowy_sezon):
                os.makedirs(nowy_sezon)
            sciezka_nowa = os.path.join(nowy_sezon, f"Finanse {nowy_sezon}.csv")

            # 3. Wczytanie danych
            df = pd.read_csv(sciezka_stara, sep=';')

            def to_num(val):
                if pd.isna(val) or val == "" : return 0.0
                if isinstance(val, str):
                    # Czyścimy tekst, ale zostawiamy minusy dla spłat
                    clean_val = val.replace('€', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
                    return float(clean_val)
                return float(val)

            df['M*'] = df['M*.1']
            df['K*'] = df['K*.1']
            
            # --- LOGIKA FINANSOWA Z RATAMI ---
            # Bierzemy 'Budżet startowy' (ostatnia kolumna, wyliczona przez run_budget_update)
            if 'Budżet startowy' in df.columns:
                df['BUDŻET STARTOWY'] = df['Budżet startowy']
            else:
                df['BUDŻET STARTOWY'] = df['BUDŻET KOŃCOWY']

            nowe_pozyczki = []
            raty_aktualizacja = []
            
            for index, row in df.iterrows():
                budzet_start = to_num(row['BUDŻET STARTOWY'])
                pozostale_raty = int(row['Raty']) if 'Raty' in df.columns else 0
                
                if budzet_start < 0 and pozostale_raty == 0:
                    nowe_pozyczki.append("1 200 000 €")
                    raty_aktualizacja.append(4)
                elif pozostale_raty > 0:
                    nowe_pozyczki.append("-300 000 €")
                    raty_aktualizacja.append(pozostale_raty - 1)
                else:
                    nowe_pozyczki.append("0 €")
                    raty_aktualizacja.append(0)

            df['Pożyczka'] = nowe_pozyczki
            df['Raty'] = raty_aktualizacja

            # --- ZEROWANIE ZMIENNYCH ---
            # Dodajemy M*.1 i K*.1 do listy kolumn do wyzerowania
            kolumny_do_wyzerowania = [
                'Konkursy', 'Nagrody', 'Roz Infr', 'Obozy Sz.', 'Juniorzy', 
                'Obozy Lecz.', 'Nadwyżka', 'M*.1', 'K*.1'
            ]
            for col in kolumny_do_wyzerowania:
                if col in df.columns:
                    # Dla zawodników wpisujemy 0, dla finansów "0 €"
                    if '*' in col:
                        df[col] = 0
                    else:
                        df[col] = "0 €"

            # Zapis pliku
            df.to_csv(sciezka_nowa, sep=';', index=False)
            
            QMessageBox.information(self, "Sukces", f"Zapisano w folderze {nowy_sezon}!\nRaty spłacających krajów ustawiono na -300 000 €.")

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Wystąpił problem: {str(e)}")

    def _browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Wybierz CSV", self._last_dir, "CSV (*.csv);;Wszystkie pliki (*.*)")
        if path:
            self.ed_path.setText(path)
            self._last_dir = str(Path(path).parent)

    def load_now(self):
        p = Path(self.ed_path.text().strip())
        if not p.exists(): return
        
        # 1. Wczytywanie i przygotowanie danych (bez zmian)
        self._df = canonicalize_headers(read_csv_loose(p))
        if 'Raty' not in self._df.columns:
            if 'Pożyczka' in self._df.columns:
                idx = self._df.columns.get_loc('Pożyczka')
                self._df.insert(idx, 'Raty', 0)
            else:
                self._df['Raty'] = 0

        # 2. Przypisanie do modelu
        self.base_model = DataFrameModel(self._df)
        self.proxy.setSourceModel(self.base_model)
        
        # Blokujemy sortowanie na czas ustawiania szerokości, żeby uniknąć błędów
        self.view.setSortingEnabled(False)

        # 3. FUNKCJA RĘCZNEGO DOPASOWANIA (Pancerna)
        def adjust_columns_manually():
            metrics = self.view.fontMetrics()
            
            # --- ZREDUKOWANE ODSTĘPY ---
            header_padding = 20  # Minimum na strzałkę sortowania i mały odstęp
            cell_padding = 25    # Mały, estetyczny margines w komórkach
            
            for i in range(self.base_model.columnCount()):
                # 1. Pomiar nagłówka
                header_text = self.base_model.headerData(i, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
                header_w = metrics.horizontalAdvance(header_text) + header_padding
                
                # 2. Pomiar danych (mierzymy to, co faktycznie widać w tabeli)
                max_cell_w = 0
                # Sprawdzamy wszystkie widoczne wiersze (lub pierwsze 100 dla wydajności)
                num_rows = min(self.proxy.rowCount(), 100)
                
                for r in range(num_rows):
                    # KLUCZ: Pobieramy dane przez proxy, żeby uwzględnić formatowanie " €"
                    idx = self.proxy.index(r, i)
                    text = str(self.proxy.data(idx, QtCore.Qt.ItemDataRole.DisplayRole) or "")
                    
                    text_w = metrics.horizontalAdvance(text) + cell_padding
                    if text_w > max_cell_w:
                        max_cell_w = text_w
                
                # 3. Wybieramy większą z wartości
                final_w = max(header_w, max_cell_w)
                
                # 4. Ustawienie szerokości
                self.view.setColumnWidth(i, final_w)
                
                # 5. Synchronizacja mrożonej tabeli (kolumny 0 i 1)
                if i < 2 and hasattr(self.view, 'frozenTableView'):
                    self.view.frozenTableView.setColumnWidth(i, final_w)

            # Aktualizacja geometrii nakładki
            if hasattr(self.view, 'frozenTableView'):
                self.view.updateFrozenTableGeometry()

            self.view.setSortingEnabled(True)
            self.view.horizontalHeader().setSortIndicator(-1, QtCore.Qt.AscendingOrder)

        # Uruchamiamy z małym opóźnieniem (100ms), aby Qt zdążyło przełknąć dane
        QtCore.QTimer.singleShot(100, adjust_columns_manually)

        # 4. SEPARATORY I STATUS (reszta Twojej logiki)
        sep_indices = [1, 3, 7, 10, 12, 14, 16, 19, 21, 23, 24, 26]
        delegate = GroupSeparatorDelegate(sep_indices, self.view)
        self.view.setItemDelegate(delegate)
        if hasattr(self.view, 'frozenTableView'):
            self.view.frozenTableView.setItemDelegate(delegate)
        
        self.view.horizontalHeader().setStretchLastSection(True)
        self._update_status()

    def _apply_filter(self):
        txt = self.ed_filter.text()
        self.proxy.setPattern(txt)
        self._update_status()

    def _clear_filter(self):
        self.ed_filter.clear()
        self.proxy.setPattern("")
        self._update_status()

    def _update_status(self):
        rows_shown = self.proxy.rowCount()
        rows_total = self.base_model.rowCount()
        sort_section = self.view.horizontalHeader().sortIndicatorSection()
        sort_order = self.view.horizontalHeader().sortIndicatorOrder()
        if sort_section >= 0 and sort_section < self.base_model.columnCount():
            sort_col = self.base_model.headerData(sort_section, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
            sort_txt = f" | sort: {sort_col} {'↑' if sort_order==QtCore.Qt.AscendingOrder else '↓'}"
        else:
            sort_txt = ""
        filt_txt = f" | filtr='{self.ed_filter.text().strip()}'" if self.ed_filter.text().strip() else ""
        self.statusBar().showMessage(f"Wiersze: {rows_shown}/{rows_total}")

    def export_view(self):
        if self.base_model.rowCount() == 0:
            QtWidgets.QMessageBox.information(self, "Eksport", "Brak danych.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Zapisz widok do CSV", "finanse_view.csv", "CSV (*.csv);;Wszystkie pliki (*.*)")
        if not path:
            return
        # collect filtered/sorted data from proxy
        rows = self.proxy.rowCount()
        cols = self.proxy.columnCount()
        data = []
        headers = [self.base_model.headerData(c, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole) for c in range(cols)]
        for r in range(rows):
            row_vals = []
            for c in range(cols):
                idx = self.proxy.index(r, c)
                row_vals.append(self.proxy.data(idx, QtCore.Qt.DisplayRole))
            data.append(row_vals)
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(headers)
                w.writerows(data)
            QtWidgets.QMessageBox.information(self, "Eksport", f"Zapisano: {path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Błąd zapisu", str(e))


def pick_initial_path():
    for p in DEFAULT_CANDIDATES:
        if Path(p).exists():
            return p
    return None

def main():
    app = QtWidgets.QApplication(sys.argv)
    init = pick_initial_path()
    win = MainWindow(init)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
