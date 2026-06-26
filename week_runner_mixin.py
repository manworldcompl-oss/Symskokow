# week_runner_mixin.py
# ---------------------------------------------------------------
# Mixin dodający funkcję "Rozegraj tydzień" do MainFrame w
# ski_jump_gui_full_embedded.py BEZ edycji wnętrza tego pliku.
#
# INSTALACJA (dwie linijki w ski_jump_gui_full_embedded.py):
#
# 1) Na górze pliku, obok innych importów lokalnych:
#
#       from week_runner_mixin import WeekRunnerMixin
#
# 2) Zmień definicję klasy z:
#
#       class MainFrame(ttk.Frame):
#
#    na:
#
#       class MainFrame(WeekRunnerMixin, ttk.Frame):
#
#    (WeekRunnerMixin musi być PIERWSZY w liście — to standardowy
#    wzorzec mixin w Pythonie, zapewnia poprawny MRO i nie wpływa na
#    __init__, bo WeekRunnerMixin go nie definiuje).
#
# To wszystko — żadna inna linia w ski_jump_gui_full_embedded.py nie
# wymaga zmian. Ten plik (oraz calendar_csv_resolver.py i
# injury_batch.py) musi leżeć w tym samym folderze.
#
# CO ROBI:
# Dodaje przycisk-wywoływaną metodę open_week_runner_dialog() (możesz
# podpiąć ją pod własny przycisk w GUI — patrz sekcja "PRZYCISK" niżej)
# oraz całą logikę: resolver czyta Kalendarz_{sezon}_{CYKL}.csv z
# self.var_calendars_dir, dla każdego przebiegu ustawia skocznię/tryb/
# listę startową, uruchamia symulację, aktualizuje klasyfikację + bazę
# SQLite (zwykłe cykle) albo panel Mistrzostw (mistrzostwa), aktualizuje
# sub-turnieje (TCS/FNT/NT/FT/RAW AIR/BB/PLANICA7/WILLINGEN5) — wszystko
# bez okienek potwierdzających — i na końcu pokazuje jeden zbiorczy
# dialog kontuzji z całego tygodnia, pogrupowany per konkurs, z
# checkboxami do zatwierdzenia przed zapisem do bazy.
#
# Braki w oryginalnym GUI, które ten mixin OMIJA bez wymagania edycji:
#   - tour_schema["FNT"] nie istnieje w oryginalnej
#     _update_tour_classification_from_preview → mixin NIE edytuje tej
#     metody; zamiast tego _week_runner_update_tour() przechwytuje
#     wywołania z tour_code="FNT" i obsługuje je samodzielnie
#     (_week_runner_save_fnt — kopia logiki oryginału z dopisanym
#     schematem FNT), a dla wszystkich innych tour_code woła oryginalną
#     metodę self._update_tour_classification_from_preview() normalnie
#     (znajdowaną przez Python przez zwykłe MRO, bo istnieje w MainFrame).
#   - FORMAT_PRESETS nie ma wpisu dla SFWC → mixin dopisuje go do
#     self._format_presets w runtime przy pierwszym użyciu (nie trzeba
#     edytować MainFrame._build).
# ---------------------------------------------------------------

from __future__ import annotations
import os
import threading
import traceback

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
from pathlib import Path

from calendar_csv_resolver import resolve_week_from_calendars, CompetitionRun, WeekResolution
from injury_batch import tag_falls_with_competition, merge_week_falls


# Preset SFWC — brakujący wpis w oryginalnym FORMAT_PRESETS
# (ski_jump_gui_full_embedded.py: MainFrame._build). Dopisywany do
# self._format_presets w runtime przez _ensure_sfwc_preset(), żeby nie
# trzeba było edytować _build.
_SFWC_PRESET_LABEL = "SFWC  (40,30,30,30 / Q:40)"
_SFWC_PRESET_VALUE = ("40,30,30,30", 40)

# Schemat sesji dla FNT — brakujący wpis w oryginalnym tour_schema
# wewnątrz _update_tour_classification_from_preview. FNT to 4 sesje:
# K1,K2 na pierwszej skoczni, K3,K4 na drugiej.
_FNT_STAGE_COLS = ["K1", "K2", "K3", "K4"]


class WeekRunnerMixin:
    """Mixin dla MainFrame. Nie definiuje __init__ — działa wyłącznie
    przez dodatkowe metody, bezpieczne do domieszania przez
    `class MainFrame(WeekRunnerMixin, ttk.Frame): ...`."""

    # =================================================================
    # PRZYCISK / WEJŚCIE
    # =================================================================
    def install_week_runner_button(self, parent_widget):
        """Wstawia przycisk '▶▶ Rozegraj tydzień' do podanego widgetu
        (np. tego samego row_week2, gdzie masz już ◀ / ▶ / ✕ Wyczyść dla
        var_week_pick). Wywołaj to raz, np. na końcu MainFrame._build,
        ALBO po prostu zignoruj i wywołuj open_week_runner_dialog() z
        własnego, ręcznie dodanego przycisku — ta metoda jest opcjonalnym
        skrótem, nie jest wymagana do działania."""
        try:
            ttk.Button(
                parent_widget,
                text="▶▶ Rozegraj tydzień",
                command=self.open_week_runner_dialog,
            ).grid(row=0, column=5, sticky="w", padx=(12, 0))
        except Exception:
            # parent_widget może używać pack zamiast grid w niektórych
            # miejscach Twojego GUI — fallback na pack, żeby się nie wywaliło
            try:
                ttk.Button(
                    parent_widget,
                    text="▶▶ Rozegraj tydzień",
                    command=self.open_week_runner_dialog,
                ).pack(side=tk.LEFT, padx=(12, 0))
            except Exception as e:
                self.log(f"[WARN] Nie udało się dodać przycisku 'Rozegraj tydzień': {e}")

    def open_week_runner_dialog(self):
        """Dialog startowy: pokazuje podgląd z resolvera zanim cokolwiek
        się uruchomi. Podepnij pod przycisk (patrz install_week_runner_button
        albo dodaj własny przycisk wołający tę metodę)."""
        try:
            week = int(self.var_week_pick.get().strip())
        except Exception:
            messagebox.showwarning("Rozegraj tydzień", "Najpierw wybierz tydzień (combo 'Tydzień').")
            return

        calendars_dir = self.var_calendars_dir.get().strip()
        if not calendars_dir or not os.path.isdir(calendars_dir):
            messagebox.showwarning(
                "Rozegraj tydzień",
                "Najpierw wskaż 'Folder kalendarzy' (ten sam, którego używasz do filtra tygodnia)."
            )
            return

        season_str = self._cls_season_var.get().strip() if hasattr(self, "_cls_season_var") else "S51"

        try:
            resolution = resolve_week_from_calendars(calendars_dir, week=week, season=season_str)
        except Exception as e:
            messagebox.showerror("Rozegraj tydzień", f"Błąd resolvera kalendarza:\n{e}")
            return

        if not resolution.runs:
            extra = ""
            if resolution.skipped:
                extra = "\n\nPominięte: " + ", ".join(resolution.skipped)
            messagebox.showinfo(
                "Rozegraj tydzień",
                f"Tydzień {week} (sezon {season_str}) nie zawiera żadnych konkursów "
                f"możliwych do rozegrania w tym GUI.{extra}"
            )
            return

        skipped_info = ""
        if resolution.skipped:
            skipped_info = "\n\nPominięte (TEAM/MIXED/nieobsłużone): " + ", ".join(resolution.skipped)

        msg = (
            f"{resolution.summary_line()}"
            f"{skipped_info}\n\n"
            f"Każdy przebieg zostanie rozegrany po kolei: skocznia z kalendarza, "
            f"lista startowa z odpowiedniej zakładki Wybór, automatyczna "
            f"aktualizacja klasyfikacji i bazy (bez pytania o potwierdzenie). "
            f"Kontuzje z całego tygodnia pokażą się do zatwierdzenia na końcu.\n\n"
            f"Kontynuować?"
        )
        if not messagebox.askyesno("Rozegraj tydzień — potwierdzenie", msg):
            return

        threading.Thread(
            target=self._week_runner_run_sequence_safe,
            args=(resolution,),
            daemon=True,
        ).start()

    # =================================================================
    # PĘTLA GŁÓWNA
    # =================================================================
    def _week_runner_run_sequence_safe(self, resolution: "WeekResolution"):
        try:
            self.set_busy(True)
            self._week_runner_run_sequence(resolution)
        except Exception:
            self.log(traceback.format_exc())
            try:
                messagebox.showerror("Rozegraj tydzień — błąd", "Wystąpił błąd – szczegóły w logu.")
            except Exception:
                pass
        finally:
            self.set_busy(False)

    def _week_runner_apply_run_setup(self, run: "CompetitionRun"):
        """Ustawia GUI (skocznia, tryb, format, lista startowa) dla
        pojedynczego przebiegu. Wykorzystuje istniejącą _on_cycle_selected
        (lista startowa wg zakładki Wybór, domyślny tryb/format), potem
        nadpisuje skocznię i tryb dokładnymi wartościami z resolvera."""
        self.var_cycle.set(run.cycle_tag)
        self._on_cycle_selected()

        if run.skocznia:
            try:
                values = list(self.cbo_hill["values"])
                match_idx = next(
                    (i for i, lbl in enumerate(values) if run.skocznia.lower() in lbl.lower()),
                    None,
                )
                if match_idx is not None:
                    self.cbo_hill.current(match_idx)
                    self._on_hill_selected()
                elif run.hs:
                    self.var_hs.set(int(float(run.hs)))
            except Exception as e:
                self.log(f"[WARN] Nie udało się dopasować skoczni '{run.skocznia}' HS{run.hs}: {e}")

        if run.mode == "classic":
            self.var_classic.set(True)
            self.var_ko50.set(False)
            self.var_ko64_full.set(False)
            if run.format_preset:
                self._week_runner_ensure_preset(run.format_preset)
                if run.format_preset in self._format_presets:
                    self.var_format_preset.set(run.format_preset)
                    cuts, spots = self._format_presets[run.format_preset]
                    self.var_round_cuts.set(cuts)
                    self.var_qual_spots.set(spots)
        elif run.mode == "ko50":
            self.var_classic.set(False)
            self.var_ko50.set(True)
            self.var_ko64_full.set(False)
        elif run.mode == "ko64":
            self.var_classic.set(False)
            self.var_ko50.set(False)
            self.var_ko64_full.set(True)

    def _week_runner_ensure_preset(self, label: str):
        """Dopisuje brakujące presety formatu (dziś: tylko SFWC) do
        self._format_presets w runtime, jeśli jeszcze ich tam nie ma —
        zastępuje konieczność edycji FORMAT_PRESETS w MainFrame._build."""
        if not hasattr(self, "_format_presets"):
            self._format_presets = {}
        if label == _SFWC_PRESET_LABEL and label not in self._format_presets:
            self._format_presets[label] = _SFWC_PRESET_VALUE

    def _week_runner_run_sequence(self, resolution: "WeekResolution"):
        week_falls_accum: list = []
        season_str = self._cls_season_var.get().strip() if hasattr(self, "_cls_season_var") else resolution.season

        total = len(resolution.runs)
        self.log(f"=== Rozegraj tydzień {resolution.week} (sezon {resolution.season}): {total} przebiegów ===")

        tour_stage_counters: dict[str, int] = {}

        for i, run in enumerate(resolution.runs, start=1):
            self.log(f"--- [{i}/{total}] {run.label()} (tryb: {run.mode}) ---")

            try:
                self._week_runner_apply_run_setup(run)
            except Exception as e:
                self.log(f"[WARN] Setup {run.label()} nieudany: {e}")
                continue

            try:
                self._run()
            except Exception as e:
                self.log(f"[BŁĄD] Symulacja {run.label()} nieudana: {e}\n{traceback.format_exc()}")
                continue

            if run.champ_info:
                try:
                    self._week_runner_export_champs(season_str, run)
                except Exception as e:
                    self.log(f"[WARN] Zapis mistrzostw {run.champ_info.name}-{run.champ_info.sex} nieudany: {e}")
            else:
                try:
                    self._week_runner_update_classification(season_str, run.cycle_tag)
                except Exception as e:
                    self.log(f"[WARN] Aktualizacja klasyfikacji {run.cycle_tag} nieudana: {e}")

            if run.tour_code:
                tour_stage_counters[run.tour_code] = tour_stage_counters.get(run.tour_code, 0) + 1
                stage_num = tour_stage_counters[run.tour_code]

                if run.needs_q1_first:
                    try:
                        self._week_runner_update_tour(season_str, run.tour_code, "Q1")
                    except Exception as e:
                        self.log(f"[WARN] Aktualizacja turnieju {run.tour_code} (Q1) nieudana: {e}")

                stage_key = f"K{stage_num}"
                try:
                    self._week_runner_update_tour(season_str, run.tour_code, stage_key)
                except Exception as e:
                    self.log(f"[WARN] Aktualizacja turnieju {run.tour_code} ({stage_key}) nieudana: {e}")

            falls_df = getattr(self, "_falls_last_df", None)
            tagged = tag_falls_with_competition(falls_df, run.cycle_tag)
            if not tagged.empty:
                week_falls_accum.append(tagged)

        self.log(f"=== Koniec tygodnia {resolution.week}: rozegrano {total} przebiegów ===")

        week_falls = merge_week_falls(week_falls_accum)
        self.after(0, lambda: self._week_runner_show_injury_dialog(resolution, week_falls, season_str))

    # =================================================================
    # AKTUALIZACJA KLASYFIKACJI (zwykłe cykle)
    # =================================================================
    def _week_runner_update_classification(self, season: str, cycle: str):
        """Cichy odpowiednik _on_update_classif_clicked — bez
        messagebox.askyesno/showinfo, tylko log. Aktualizuje pliki
        klasyfikacji ORAZ statystyki kariery/rekordy w manager_skokow.db."""
        n_players, n_nations, root = self._update_classifications_from_preview(season, cycle)
        is_ski_flying = cycle.strip().upper().startswith("SKI_FLYING")

        if is_ski_flying:
            self.log(f"[KLASYFIKACJA] {cycle}: zawodnicy={n_players}, kraje=brak (Ski Flying)")
            return

        raport = aktualizuj_najnowszy_wynik(
            sezon=season,
            typ_cyklu=cycle,
            wyniki_folder="./wyniki",
            db_path="manager_skokow.db",
        )
        extra = []
        if raport.get("nowe_rekordy_skoczni", 0):
            extra.append(f"rekordy skoczni: {raport['nowe_rekordy_skoczni']}")
        if raport.get("nowe_rekordy_swiata", 0):
            extra.append("NOWY REKORD ŚWIATA")
        if raport.get("nowe_rekordy_krajowe", 0):
            extra.append(f"rekordy krajowe: {raport['nowe_rekordy_krajowe']}")
        extra_txt = (" | " + ", ".join(extra)) if extra else ""
        self.log(
            f"[KLASYFIKACJA] {cycle}: zawodnicy={n_players}, kraje={n_nations}, "
            f"baza: zaktualizowano {raport['zaktualizowano']} zawodników "
            f"(skocznia: {raport['skocznia']}){extra_txt}"
        )

    # =================================================================
    # AKTUALIZACJA SUB-TURNIEJÓW (TCS/FNT/NT/FT/RAW AIR/BB/P7/W5)
    # =================================================================
    def _week_runner_update_tour(self, season: str, tour_code: str, stage_key: str):
        """Cichy wrapper na _update_tour_classification_from_preview —
        ale dla tour_code='FNT' obsługuje to SAMODZIELNIE (kopia logiki
        oryginalnej metody z dopisanym schematem FNT), bo oryginalny
        tour_schema w ski_jump_gui_full_embedded.py go nie ma, a ten
        mixin celowo nie edytuje oryginalnego pliku."""
        if tour_code == "FNT":
            n_rows, path = self._week_runner_save_fnt(season, stage_key)
        else:
            n_rows, path = self._update_tour_classification_from_preview(season, tour_code, stage_key)
        self.log(f"[TURNIEJ] {tour_code} ({stage_key}): {n_rows} zawodników → {path}")

    def _week_runner_save_fnt(self, season: str, stage_key: str):
        """Reimplementacja _update_tour_classification_from_preview
        wyłącznie dla tour_code='FNT' (4 sesje: K1,K2 na 1. skoczni,
        K3,K4 na 2.) — identyczna logika jak oryginał, tylko z FNT
        dopisanym do lokalnego tour_schema zamiast edycji oryginału."""
        season = str(season or "").strip()
        stage_key = str(stage_key or "").strip().upper()
        if stage_key not in {"K1", "K2", "K3", "K4"}:
            raise ValueError("FNT: sesja musi być jedną z K1..K4.")

        d = getattr(self, "_last_final_cls", None)
        if d is None or len(d) == 0:
            raise RuntimeError("Brak ostatniej klasyfikacji konkursu. Uruchom najpierw konkurs FNT.")

        d = d.copy()
        for c in ("Zawodnik", "Kraj"):
            if c not in d.columns:
                raise RuntimeError(f"Klasyfikacja końcowa nie zawiera kolumny: {c}")
        d["Zawodnik"] = d["Zawodnik"].astype(str)
        d["Kraj"] = d["Kraj"].astype(str).str.upper().str.strip()

        if "Punkty" in d.columns:
            pts = pd.to_numeric(d["Punkty"], errors="coerce").fillna(0.0)
        elif "Punkty FIS" in d.columns:
            pts = pd.to_numeric(d["Punkty FIS"], errors="coerce").fillna(0.0)
        else:
            scale = [100,80,60,50,45,40,36,32,29,26,24,22,20,18,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1]
            m = pd.to_numeric(d.get("Miejsce", None), errors="coerce")
            pts = m.map(lambda x: scale[int(x)-1] if pd.notna(x) and 1 <= int(x) <= len(scale) else 0)
            pts = pd.to_numeric(pts, errors="coerce").fillna(0.0)
        d = d.assign(__PTS__=pts)

        stage_cols = _FNT_STAGE_COLS
        root = Path(f"./{season}/Klasyfikacje {season}").resolve()
        root.mkdir(parents=True, exist_ok=True)
        tour_path = root / f"{season}_FNT.csv"

        def _read_csv_loose(p: Path) -> pd.DataFrame:
            if not p.exists():
                return pd.DataFrame()
            for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
                try:
                    return pd.read_csv(p, sep=None, engine="python", encoding=enc)
                except Exception:
                    continue
            try:
                return pd.read_csv(p, sep=";", encoding="utf-8")
            except Exception:
                return pd.DataFrame()

        cur = _read_csv_loose(tour_path)
        cur_cols = [str(c).strip() for c in cur.columns] if not cur.empty else []
        if not cur_cols or "JUMPER" not in cur_cols or "NAT" not in cur_cols:
            cur = pd.DataFrame(columns=["LP.", "JUMPER", "NAT"] + stage_cols + ["Overall"])
        else:
            cur = cur.copy()
            cur.columns = cur_cols
            for c in stage_cols:
                if c not in cur.columns:
                    cur[c] = 0.0
            if "Overall" not in cur.columns:
                cur["Overall"] = 0.0
            if "LP." not in cur.columns:
                cur.insert(0, "LP.", range(1, len(cur) + 1))

        cur["NAT"] = cur.get("NAT", "").astype(str).str.upper().str.strip()

        add = d[["Zawodnik", "Kraj", "__PTS__"]].copy()
        add.rename(columns={"Zawodnik": "JUMPER", "Kraj": "NAT", "__PTS__": "__ADD__"}, inplace=True)
        add["NAT"] = add["NAT"].astype(str).str.upper().str.strip()

        merged = cur.merge(add, on=["JUMPER", "NAT"], how="outer")
        merged["__ADD__"] = pd.to_numeric(merged["__ADD__"], errors="coerce").fillna(0.0)

        merged[stage_key] = pd.to_numeric(merged.get(stage_key, 0.0), errors="coerce").fillna(0.0)
        merged[stage_key] = merged["__ADD__"]
        merged.drop(columns=["__ADD__"], inplace=True)

        for c in stage_cols:
            merged[c] = pd.to_numeric(merged.get(c, 0.0), errors="coerce").fillna(0.0)
        merged["Overall"] = merged[stage_cols].sum(axis=1)

        merged["JUMPER"] = merged.get("JUMPER", "").astype(str)
        merged["NAT"] = merged.get("NAT", "").astype(str)
        mask_keep = (
            merged["JUMPER"].str.strip().ne("") |
            merged["NAT"].str.strip().ne("") |
            (merged["Overall"] != 0)
        )
        merged = merged.loc[mask_keep].copy()

        merged = merged.sort_values(
            by=["Overall", "JUMPER", "NAT"],
            ascending=[False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)

        if "LP." in merged.columns:
            merged.drop(columns=["LP."], inplace=True)
        merged.insert(0, "LP.", range(1, len(merged) + 1))

        ordered_cols = ["LP.", "JUMPER", "NAT"] + stage_cols + ["Overall"]
        tail = [c for c in merged.columns if c not in ordered_cols]
        merged = merged[ordered_cols + tail]

        merged.to_csv(tour_path, sep=";", encoding="utf-8-sig", index=False)
        return len(merged), str(tour_path)

    # =================================================================
    # PANEL MISTRZOSTW (OG/WCH/SFWC/UNI/YOG/COCH/JWC/NKIC/IST)
    # =================================================================
    def _week_runner_export_champs(self, season: str, run: "CompetitionRun"):
        """Cichy odpowiednik _export_champs_results — ustawia pola
        panelu Mistrzostw (dla spójności widoku GUI) i zapisuje CSV bez
        messagebox.showinfo/showwarning/showerror. Woła dwukrotnie:
        najpierw 'QUAL' (self._last_qual_cls), potem 'FINAL'
        (self._last_final_cls albo self._last_ko64_cls dla IST)."""
        ci = run.champ_info
        if ci is None:
            return

        self._champs_season_var.set(season)
        self._cb_ch_name.set(ci.name)
        self._champs_name_var.set(ci.name)
        self._cb_ch_sex.set(ci.sex)
        self._champs_sex_var.set(ci.sex)
        self._cb_ch_type.set("IND")
        self._champs_type_var.set("IND")
        self._cb_ch_hill.set(ci.hill)
        self._champs_hill_var.set(ci.hill)
        self._champs_ko64_var.set(bool(ci.ko64))

        def _save_one(mode: str):
            comp_type = "Q" if mode == "QUAL" else "IND"
            parts = [season, ci.name, ci.sex, comp_type, ci.hill]
            clean_parts = [p for p in parts if p and p.strip()]
            code = "_".join(clean_parts).upper()

            if mode == "QUAL":
                src = getattr(self, "_last_qual_cls", None)
                src_label = "kwalifikacji"
            elif ci.ko64:
                src = getattr(self, "_last_ko64_cls", None)
                src_label = "KO64"
            else:
                src = getattr(self, "_last_final_cls", None)
                src_label = "konkursu"

            if src is None or not isinstance(src, pd.DataFrame) or src.empty:
                self.log(f"[MISTRZOSTWA] {code}: brak danych {src_label} — pominięto zapis.")
                return

            df = src.copy()
            try:
                if "Miejsce" in df.columns:
                    df = df.sort_values("Miejsce")
            except Exception:
                pass

            root = Path(".") / season / f"Mistrzostwa {season}"
            try:
                root.mkdir(parents=True, exist_ok=True)
                path = root / f"{code}.csv"
                df.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
                self.log(f"[MISTRZOSTWA] {code}: zapisano {src_label} → {path}")
            except Exception as e:
                self.log(f"[BŁĄD] Zapis mistrzostw {code} nieudany: {e}")

        _save_one("QUAL")
        _save_one("FINAL")

    # =================================================================
    # ZBIORCZY DIALOG KONTUZJI TYGODNIA
    # =================================================================
    def _week_runner_show_injury_dialog(self, resolution: "WeekResolution", week_falls, season: str):
        """Zbiorczy dialog kontuzji z całego tygodnia, pogrupowany
        sekcjami per konkurs. Checkboxy per wiersz, zaznacz/odznacz
        globalnie i per sekcja, zatwierdzenie zapisuje TYLKO zaznaczone
        do bazy zawodników i Kontuzje S{sezon}.csv."""
        if week_falls is None or getattr(week_falls, "empty", True):
            messagebox.showinfo(
                "Rozegraj tydzień — gotowe",
                f"Tydzień {resolution.week} rozegrany. Brak kontuzji do zatwierdzenia."
            )
            return

        top = tk.Toplevel(self)
        top.title(f"Kontuzje tygodnia {resolution.week} ({season})")
        top.geometry("1000x640")
        top.resizable(True, True)
        try:
            top.grab_set()
        except Exception:
            pass

        hdr = ttk.Frame(top)
        hdr.pack(fill=tk.X, padx=10, pady=(8, 0))
        ttk.Label(
            hdr,
            text=(
                f"Zaznacz kontuzje, które są PRAWDZIWE i mają trafić do bazy danych.\n"
                f"Tydzień: {resolution.week}  |  Sezon: {season}  |  "
                f"Przebiegów: {len(resolution.runs)}  |  Łącznie kontuzjowanych: {len(week_falls)}"
            ),
            wraplength=940, justify=tk.LEFT,
        ).pack(side=tk.LEFT)

        tool = ttk.Frame(top)
        tool.pack(fill=tk.X, padx=10, pady=(4, 0))

        check_vars: list[tuple[tk.BooleanVar, dict]] = []
        section_vars: dict[str, list[tk.BooleanVar]] = {}

        lbl_count = ttk.Label(tool, text="")
        lbl_count.pack(side=tk.RIGHT, padx=(0, 4))

        def _update_count(*_):
            n = sum(1 for v, _ in check_vars if v.get())
            lbl_count.config(text=f"Zaznaczono: {n}/{len(check_vars)}")

        def _select_all():
            for v, _ in check_vars:
                v.set(True)
            _update_count()

        def _deselect_all():
            for v, _ in check_vars:
                v.set(False)
            _update_count()

        ttk.Button(tool, text="✔ Zaznacz wszystkie", command=_select_all).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(tool, text="✕ Odznacz wszystkie", command=_deselect_all).pack(side=tk.LEFT)

        canvas_frame = ttk.Frame(top)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 4))

        canvas = tk.Canvas(canvas_frame, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_configure)

        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_resize)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        headers = ["", "Zawodnik", "Kraj", "Kontuzja (rodzaj)", "Kontuzja (dni)", "ΔUM", "ΔForma"]
        col_widths = [3, 26, 6, 16, 14, 6, 7]

        grouped = week_falls.groupby("Zawody", sort=False)
        row_i = 0
        for cycle_tag, df_g in grouped:
            sec_frame = ttk.Frame(inner)
            sec_frame.grid(row=row_i, column=0, columnspan=len(headers), sticky="ew", pady=(10 if row_i else 0, 2), padx=4)
            row_i += 1

            ttk.Label(sec_frame, text=f"— {cycle_tag} ({len(df_g)}) —", font=(None, 10, "bold")).pack(side=tk.LEFT)

            def _make_section_toggle(tag=cycle_tag, value=True):
                def _toggle():
                    for v in section_vars.get(tag, []):
                        v.set(value)
                    _update_count()
                return _toggle

            ttk.Button(sec_frame, text="zaznacz", width=8, command=_make_section_toggle(value=True)).pack(side=tk.LEFT, padx=(8, 2))
            ttk.Button(sec_frame, text="odznacz", width=8, command=_make_section_toggle(value=False)).pack(side=tk.LEFT)

            hdr_row = ttk.Frame(inner)
            hdr_row.grid(row=row_i, column=0, columnspan=len(headers), sticky="ew", padx=4)
            row_i += 1
            for ci_, (htext, w) in enumerate(zip(headers, col_widths)):
                ttk.Label(hdr_row, text=htext, width=w, font=(None, 9, "italic")).grid(row=0, column=ci_, sticky="w")

            for _, row in df_g.iterrows():
                row_dict = row.to_dict()
                var = tk.BooleanVar(value=True)
                check_vars.append((var, row_dict))
                section_vars.setdefault(cycle_tag, []).append(var)

                line = ttk.Frame(inner)
                line.grid(row=row_i, column=0, columnspan=len(headers), sticky="ew", padx=4)
                row_i += 1

                ttk.Checkbutton(line, variable=var, command=_update_count).grid(row=0, column=0, sticky="w")
                values = [
                    str(row_dict.get("Zawodnik", "")),
                    str(row_dict.get("Kraj", "")),
                    str(row_dict.get("Kontuzja (rodzaj)", "")),
                    str(row_dict.get("Kontuzja (dni)", "")),
                    str(row_dict.get("ΔUM (kontuzja)", "")),
                    str(row_dict.get("ΔForma (kontuzja)", "")),
                ]
                for ci_, (val, w) in enumerate(zip(values, col_widths[1:]), start=1):
                    ttk.Label(line, text=val, width=w).grid(row=0, column=ci_, sticky="w")

        _update_count()

        btns = ttk.Frame(top)
        btns.pack(fill=tk.X, padx=10, pady=(4, 10))

        def _on_cancel():
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
            top.destroy()

        def _on_confirm():
            selected_rows = [row for v, row in check_vars if v.get()]
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
            top.destroy()
            if not selected_rows:
                messagebox.showinfo("Kontuzje tygodnia", "Nie zaznaczono żadnych kontuzji — baza nie została zmieniona.")
                return
            try:
                self._week_runner_commit_injuries(selected_rows, resolution, season)
            except Exception as e:
                messagebox.showerror("Kontuzje tygodnia — błąd zapisu", str(e))

        ttk.Button(btns, text="Anuluj", command=_on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btns, text="Zatwierdź zaznaczone → zapisz do bazy", command=_on_confirm).pack(side=tk.RIGHT)

        try:
            top.update_idletasks()
            top.lift(); top.focus_force()
        except Exception:
            pass

    def _week_runner_commit_injuries(self, selected_rows: list[dict], resolution: "WeekResolution", season: str):
        """Zapisuje zaznaczone kontuzje do bazy zawodników i Kontuzje
        S{sezon}.csv, używając istniejącego _apply_injury_updates_to_db
        zbiorczo dla wielu przebiegów naraz."""
        falls_agg = pd.DataFrame(selected_rows)
        if falls_agg.empty:
            return

        self._falls_last_agg = falls_agg
        self._falls_last_df = falls_agg

        event_name = f"TYDZIEN_{resolution.week}_{season}"
        week_val = resolution.week

        self._apply_injury_updates_to_db(event_name, week_val)
        self.log(f"[KONTUZJE] Zapisano {len(falls_agg)} kontuzji z tygodnia {resolution.week} do bazy.")
