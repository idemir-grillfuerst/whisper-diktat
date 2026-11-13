"""Reiter „Befehle“: alle Sprachbefehle als Tabelle mit Suche, Filter und Neu/Ändern/Löschen.

Jede Änderung wird sofort in befehle.toml gespeichert (in den frisch gelesenen Dateitext, Kommentare bleiben).
"""
import tkinter as tk
from tkinter import ttk

from ..befehle import normalisiere
from ..config import schreibe_atomar
from . import stil
from .daten import ARTEN_LESBAR, Befehl, lies_befehle, setze_befehl, wirkung_lesbar
from .dialoge import befehl_bearbeiten
from .fenster import Reiter

FILTER = (("", "Alle"), ("oeffnen", "Öffnen"), ("tasten", "Tasten"), ("aktionen", "Aktionen"))


def filtere(befehle: list[Befehl], suche: str, art: str | None) -> list[Befehl]:
    s = suche.strip().lower()
    erg = []
    for b in befehle:
        if art and b.art != art:
            continue
        if s and s not in " ".join(b.saetze).lower() and s not in b.ziel.lower() \
                and s not in wirkung_lesbar(b).lower() and normalisiere(s) not in normalisiere(" ".join(b.saetze)):
            continue
        erg.append(b)
    return erg


class BefehleReiter(Reiter):
    titel = "Befehle"

    def __init__(self, eltern, fenster):
        super().__init__(eltern, fenster)
        self.befehle: list[Befehl] = []
        self._sichtbar: list[Befehl] = []
        f = ttk.Frame(self, padding=(stil.px(22), stil.px(16)))
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(3, weight=1)
        ttk.Label(f, text="Sprachbefehle", style="Ueberschrift.TLabel").grid(row=0, column=0, sticky="w")
        stil.erklaerung(f, "Ein Befehl wirkt nur, wenn das ganze Diktat genau einer seiner Sätze ist – „Bitte mach das "
                        "rückgängig“ bleibt Text. Bei „Öffnen“ gehen automatisch alle Satzformen („öffne X“, "
                        "„X öffnen“, „zeig mir X“ …). Die Wörter zum Absenden („Senden“) stehen im Reiter Allgemein. "
                        "Änderungen hier werden sofort gespeichert.").grid(row=1, column=0, sticky="w", pady=(2, 10))

        leiste = ttk.Frame(f)
        leiste.grid(row=2, column=0, sticky="we", pady=(0, 8))
        self.suche = tk.StringVar()
        ttk.Label(leiste, text="Suchen:").pack(side="left")
        ttk.Entry(leiste, textvariable=self.suche, width=24).pack(side="left", padx=(6, 16))
        self.art = tk.StringVar(value="")
        for wert, text in FILTER:
            ttk.Radiobutton(leiste, text=text, value=wert, variable=self.art, command=self._fuellen).pack(
                side="left", padx=(0, 10))
        self.suche.trace_add("write", lambda *a: self._fuellen())

        tab = ttk.Frame(f)
        tab.grid(row=3, column=0, sticky="nsew")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.tabelle = ttk.Treeview(tab, columns=("saetze", "art", "wirkung"), show="headings", selectmode="browse")
        for spalte, text, breite in (("saetze", "Sätze", 340), ("art", "Art", 90), ("wirkung", "Wirkung", 340)):
            self.tabelle.heading(spalte, text=text)
            self.tabelle.column(spalte, width=stil.px(breite), stretch=spalte != "art")
        balken = ttk.Scrollbar(tab, orient="vertical", command=self.tabelle.yview)
        self.tabelle.configure(yscrollcommand=balken.set)
        self.tabelle.grid(row=0, column=0, sticky="nsew")
        balken.grid(row=0, column=1, sticky="ns")
        self.tabelle.bind("<Double-1>", lambda e: self.aendern())
        self.tabelle.bind("<Delete>", lambda e: self.loeschen())

        knoepfe = ttk.Frame(f)
        knoepfe.grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Button(knoepfe, text="Neu …", style="Accent.TButton", command=self.neu).pack(side="left")
        ttk.Button(knoepfe, text="Ändern …", command=self.aendern).pack(side="left", padx=(8, 0))
        ttk.Button(knoepfe, text="Löschen", command=self.loeschen).pack(side="left", padx=(8, 0))
        self.anzahl = ttk.Label(knoepfe, style="Erklaerung.TLabel")
        self.anzahl.pack(side="left", padx=(16, 0))

    # --- Daten ----------------------------------------------------------------------------------------------------
    def _datei(self):
        return self.fenster.dateien["befehle"]

    def _text(self) -> str:
        d = self._datei()
        return d.read_text(encoding="utf-8") if d.exists() else ""

    def laden(self):
        try:
            self.befehle = lies_befehle(self._text())
        except (OSError, ValueError) as e:
            self.befehle = []
            self.fenster.zeige_fehler(f"befehle.toml lässt sich nicht lesen: {e}")
        self._fuellen()

    def _fuellen(self):
        self.tabelle.delete(*self.tabelle.get_children())
        self._sichtbar = filtere(self.befehle, self.suche.get(), self.art.get() or None)
        for i, b in enumerate(self._sichtbar):
            saetze = b.saetze[0] + (f"   (+{len(b.saetze) - 1})" if len(b.saetze) > 1 else "")
            self.tabelle.insert("", "end", iid=str(i), values=(saetze, ARTEN_LESBAR[b.art], wirkung_lesbar(b)))
        self.anzahl.configure(text=f"{len(self._sichtbar)} von {len(self.befehle)} Befehlen")

    def _ausgewaehlt(self) -> Befehl | None:
        sel = self.tabelle.selection()
        return self._sichtbar[int(sel[0])] if sel else None

    # --- Aktionen (sofort gespeichert) ----------------------------------------------------------------------------------
    def bestaetigen(self, text: str) -> bool:
        from tkinter import messagebox
        return messagebox.askyesno("Befehl löschen", text, parent=self)

    def speichern(self, alt: Befehl | None, neu: Befehl | None) -> bool:
        try:
            text = setze_befehl(self._text(), alt, neu)
            schreibe_atomar(self._datei(), text)
        except (OSError, ValueError) as e:
            self.fenster.zeige_fehler(f"Befehl konnte nicht gespeichert werden:\n{e}")
            return False
        self.laden()
        self.fenster.status.configure(text="Befehl gespeichert – gilt ab dem nächsten Diktat.")
        return True

    def neu(self):
        b = befehl_bearbeiten(self, None, self.befehle, self._text())
        if b:
            self.speichern(None, b)

    def aendern(self):
        alt = self._ausgewaehlt()
        if alt is None:
            return
        b = befehl_bearbeiten(self, alt, self.befehle, self._text())
        if b:
            b.schluessel = alt.schluessel
            self.speichern(alt, b)

    def loeschen(self, befehl: Befehl | None = None):
        befehl = befehl or self._ausgewaehlt()
        if befehl is None:
            return
        if self.bestaetigen(f"„{befehl.saetze[0]}“ ({wirkung_lesbar(befehl)}) wirklich löschen?"):
            self.speichern(befehl, None)
