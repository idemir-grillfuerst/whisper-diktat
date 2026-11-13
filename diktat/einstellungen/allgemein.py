"""Reiter „Allgemein“: Tastenkombination, Bedienung, Maus, Einfügen, Absenden-Wörter, Autostart, Erweitert."""
import tkinter as tk
from tkinter import ttk

from .. import autostart
from . import daten, stil
from .dialoge import tasten_waehlen
from .fenster import KonfigReiter

MODUS_TEXT = {
    "halten": ("Halten", "Gedrückt halten = Aufnahme, loslassen = fertig."),
    "umschalten": ("Umschalten", "Einmal tippen startet, nochmal tippen beendet."),
    "beides": ("Beides", "Lang halten diktiert wie „Halten“, kurz tippen startet eine Daueraufnahme bis zum "
                         "nächsten Tippen."),
}


class Allgemein(KonfigReiter):
    titel = "Allgemein"
    felder = ("shortcut", "modus", "tipp_grenze_s", "maustaste", "einfuegen", "leerzeichen_danach", "enter",
              "max_aufnahme_s", "min_dauer_s", "leerlauf_minuten", "aufnahmen_speichern")

    def __init__(self, eltern, fenster):
        super().__init__(eltern, fenster)
        self.ueberschrift("Diktieren starten")
        self.feld("shortcut", steuer=self._shortcut_steuer)
        self.feld("modus", steuer=self._modus_steuer)
        self.feld("tipp_grenze_s")
        self.feld("maustaste")
        self.var["modus"].trace_add("write", lambda *a: self._tipp_grenze_zeigen())

        self.ueberschrift("Nach dem Diktat")
        self.feld("einfuegen")
        self.feld("leerzeichen_danach")
        self.feld("enter")

        self.ueberschrift("Windows")
        self.autostart = tk.BooleanVar()
        z = ttk.Frame(self.innen)
        z.grid(row=self._zeile, column=0, sticky="we", pady=(10, 0))
        self._zeile += 1
        self._autostart_knopf = ttk.Checkbutton(z, text="Mit Windows starten", variable=self.autostart,
                                                style="Switch.TCheckbutton", command=self._autostart_umschalten)
        self._autostart_knopf.grid(row=0, column=0, sticky="w")
        self._autostart_status = ttk.Label(z, style="Erklaerung.TLabel")
        self._autostart_status.grid(row=0, column=1, sticky="w", padx=8)
        stil.erklaerung(z, "Startet whisper-diktat bei der Anmeldung und nach dem Entsperren automatisch (Aufgabe "
                        "„whisper-diktat“ in der Windows-Aufgabenplanung). Wirkt sofort.").grid(row=1, column=0,
                                                                                               columnspan=2,
                                                                                               sticky="w")

        self.erweitert = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.innen, text="Erweiterte Einstellungen anzeigen", variable=self.erweitert,
                        command=self._erweitert_zeigen).grid(row=self._zeile, column=0, sticky="w", pady=(22, 0))
        self._zeile += 1
        self._erweitert_zeilen = [self.feld(n) for n in ("max_aufnahme_s", "min_dauer_s", "leerlauf_minuten",
                                                         "aufnahmen_speichern")]
        self._erweitert_zeigen()

    # --- Steuerelemente -------------------------------------------------------------------------------------------
    def _shortcut_steuer(self, eltern):
        f = ttk.Frame(eltern)
        anzeige = ttk.Label(f, style="Titel.TLabel", width=24)
        anzeige.pack(side="left")
        ttk.Button(f, text="Ändern …", command=self._shortcut_aendern).pack(side="left", padx=(8, 0))
        self.var["shortcut"].trace_add("write", lambda *a: anzeige.configure(
            text=daten.tasten_lesbar(self.var["shortcut"].get()) or "–"))
        return f

    def _shortcut_aendern(self):
        neu = tasten_waehlen(self, self.var["shortcut"].get(), nur_zusatz_erlaubt=True,
                             titel="Tastenkombination zum Diktieren")
        if neu:
            self.var["shortcut"].set(neu)

    def _modus_steuer(self, eltern):
        f = ttk.Frame(eltern)
        for i, (wert, (titel, text)) in enumerate(MODUS_TEXT.items()):
            ttk.Radiobutton(f, text=titel, value=wert, variable=self.var["modus"]).grid(row=2 * i, column=0,
                                                                                        sticky="w", pady=(4, 0))
            stil.erklaerung(f, text).grid(row=2 * i + 1, column=0, sticky="w", padx=(stil.px(28), 0))
        return f

    def _tipp_grenze_zeigen(self):
        z = self._zeilen.get("tipp_grenze_s")
        if z is not None:
            (z.grid if self.var["modus"].get() == "beides" else z.grid_remove)()

    def _erweitert_zeigen(self):
        for z in self._erweitert_zeilen:
            (z.grid if self.erweitert.get() else z.grid_remove)()

    # --- Autostart (wirkt sofort, nicht über Übernehmen) -------------------------------------------------------------
    def laden(self):
        super().laden()
        self._tipp_grenze_zeigen()
        self._autostart_knopf.state(["disabled"])
        self._autostart_status.configure(text="wird geprüft …")

        self.im_hintergrund(autostart.ist_aktiv, self._autostart_zeigen)

    def _autostart_zeigen(self, an):
        if not isinstance(an, bool):
            self._autostart_status.configure(text="Status unbekannt")
        else:
            self.autostart.set(an)
            self._autostart_status.configure(text="")
        self._autostart_knopf.state(["!disabled"])

    def _autostart_umschalten(self):
        an = self.autostart.get()
        self._autostart_knopf.state(["disabled"])
        self._autostart_status.configure(text="wird eingerichtet …" if an else "wird ausgeschaltet …")

        self.im_hintergrund(autostart.aktivieren if an else autostart.deaktivieren,
                            lambda erg: self._autostart_fertig(an, erg))

    def _autostart_fertig(self, an: bool, erg):
        self._autostart_knopf.state(["!disabled"])
        fehler = str(erg) if isinstance(erg, Exception) else None
        if fehler:
            self.autostart.set(not an)
            self._autostart_status.configure(text="")
            self.fenster.zeige_fehler(f"Autostart konnte nicht geändert werden:\n{fehler}")
        else:
            self._autostart_status.configure(text="eingeschaltet" if an else "ausgeschaltet")
