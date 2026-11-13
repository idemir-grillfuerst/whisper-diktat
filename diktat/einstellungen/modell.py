"""Reiter „Modell“: Whisper-Modell, Recheneinheit (Grafik/NPU/CPU), Sprache."""
from tkinter import ttk

from .. import geraete
from ..config import lade_config_text
from .fenster import KonfigReiter

GERAET_TEXT = {"GPU": "Grafik", "NPU": "NPU (KI-Beschleuniger)", "CPU": "Prozessor"}


class Modell(KonfigReiter):
    titel = "Modell"
    felder = ("modell", "geraet", "sprache")

    def __init__(self, eltern, fenster):
        super().__init__(eltern, fenster)
        self._einheiten: list[tuple[str, str]] = []
        self.ueberschrift("Whisper", "Änderungen hier lädt das Tool im Hintergrund neu (einige Sekunden). Du kannst "
                                     "währenddessen weiter diktieren, der Text kommt dann etwas später.")
        self._modell_rahmen = None
        self.feld("modell", steuer=self._modell_steuer)
        self.feld("geraet", steuer=self._geraet_steuer)
        self.feld("sprache")
        self.var["geraet"].trace_add("write", lambda *a: self._geraet_zeigen())

    def _modell_steuer(self, eltern):
        self._modell_rahmen = ttk.Frame(eltern)
        return self._modell_rahmen

    def _geraet_steuer(self, eltern):
        f = ttk.Frame(eltern)
        self.geraet_box = ttk.Combobox(f, state="readonly", width=44, values=["Automatisch", "wird gesucht …"])
        self.geraet_box.pack(side="left")
        self.geraet_box.bind("<<ComboboxSelected>>", self._geraet_gewaehlt)
        self._npu = ttk.Label(f, style="Neustart.TLabel")
        self._npu.pack(side="left", padx=(8, 0))
        return f

    def laden(self):
        try:
            modelle = lade_config_text(self._datei().read_text(encoding="utf-8")).modelle
        except (OSError, ValueError):
            modelle = {}
        for w in self._modell_rahmen.winfo_children():
            w.destroy()
        for name, m in modelle.items():
            ttk.Radiobutton(self._modell_rahmen, text=m.titel, value=name, variable=self.var["modell"]).pack(
                anchor="w", pady=(2, 0))
        super().laden()
        # Import von OpenVINO dauert ~1 s: im Hintergrund suchen
        self.im_hintergrund(lambda: geraete.recheneinheiten(), self._einheiten_zeigen)

    def _einheiten_zeigen(self, liste):
        self._einheiten = liste if isinstance(liste, list) else [("CPU", "Prozessor")]
        self._geraet_zeigen()

    def _geraet_zeigen(self):
        aktuell = self.var["geraet"].get() or "auto"
        werte = ["auto"] + [g for g, _ in self._einheiten]
        if aktuell not in werte:
            werte.append(aktuell)
        auto = geraete.loese_geraet("auto", self._einheiten) if self._einheiten else None
        anzeigen = [f"Automatisch (jetzt {GERAET_TEXT.get(auto.split('.')[0], auto)})" if auto else "Automatisch"]
        for g in werte[1:]:
            name = dict(self._einheiten).get(g, "nicht gefunden")
            anzeigen.append(f"{GERAET_TEXT.get(g.split('.')[0], g)} – {name}")
        if not self._einheiten:
            anzeigen.append("wird gesucht …")
        self._geraet_werte = werte
        self.geraet_box.configure(values=anzeigen)
        if aktuell in werte:
            self.geraet_box.current(werte.index(aktuell))
        self._npu.configure(text="erstes Laden dauert Minuten" if aktuell.startswith("NPU") else "")

    def _geraet_gewaehlt(self, _e=None):
        i = self.geraet_box.current()
        if 0 <= i < len(self._geraet_werte):
            self.var["geraet"].set(self._geraet_werte[i])
        else:
            self._geraet_zeigen()


