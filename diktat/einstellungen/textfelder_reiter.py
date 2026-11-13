"""Reiter „Textfelder“: die per „merke Textfeld“ gemerkten Felder ansehen und löschen."""
import os
from tkinter import messagebox, ttk

from . import stil
from .daten import regel_loeschen, regeln_liste
from .fenster import Reiter


class TextfelderReiter(Reiter):
    titel = "Textfelder"

    def __init__(self, eltern, fenster):
        super().__init__(eltern, fenster)
        f = ttk.Frame(self, padding=(stil.px(22), stil.px(16)))
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)
        ttk.Label(f, text="Gemerkte Textfelder", style="Ueberschrift.TLabel").grid(row=0, column=0, sticky="w")
        stil.erklaerung(f, "„Textfeld“ findet das Eingabefeld meist von selbst. Hat es einmal das falsche erwischt: "
                        "Maus auf das richtige Feld, „merke Textfeld“ sagen – dann steht es hier. „vergiss Textfeld“ "
                        "oder „Löschen“ nimmt es wieder raus. Bei Browsern gilt eine Regel nur für die Website.").grid(
            row=1, column=0, sticky="w", pady=(2, 10))
        self.liste = ttk.Treeview(f, columns=("wo", "was"), show="headings", selectmode="browse", height=8)
        self.liste.heading("wo", text="Programm / Website")
        self.liste.heading("was", text="Gemerkt")
        self.liste.column("wo", width=stil.px(320))
        self.liste.column("was", width=stil.px(360))
        self.liste.grid(row=2, column=0, sticky="nsew")
        self.liste.bind("<Delete>", lambda e: self.loeschen())
        knoepfe = ttk.Frame(f)
        knoepfe.grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Button(knoepfe, text="Löschen", command=self.loeschen).pack(side="left")
        ttk.Button(knoepfe, text="Datei öffnen …", command=self._datei_oeffnen).pack(side="left", padx=(8, 0))
        self._leer = ttk.Label(f, style="Erklaerung.TLabel", text="Noch keine Textfelder gemerkt.")

    def _datei(self):
        return self.fenster.dateien["textfelder"]

    def _text(self) -> str:
        d = self._datei()
        return d.read_text(encoding="utf-8") if d.exists() else ""

    def laden(self):
        self.liste.delete(*self.liste.get_children())
        try:
            eintraege = regeln_liste(self._text())
        except (OSError, ValueError) as e:
            self.fenster.zeige_fehler(f"textfelder.toml lässt sich nicht lesen: {e}")
            eintraege = []
        for schl, was in eintraege:
            wo = schl.replace("|", " – ")
            self.liste.insert("", "end", iid=schl, values=(wo, was))
        (self._leer.grid(row=4, column=0, sticky="w", pady=(8, 0)) if not eintraege else self._leer.grid_remove())

    def bestaetigen(self, text: str) -> bool:
        return messagebox.askyesno("Textfeld vergessen", text, parent=self)

    def loeschen(self, schluessel: str | None = None):
        sel = self.liste.selection()
        schluessel = schluessel or (sel[0] if sel else None)
        if not schluessel or not self.bestaetigen(f"Gemerktes Textfeld für „{schluessel}“ löschen?"):
            return
        try:
            self._datei().write_text(regel_loeschen(self._text(), schluessel), encoding="utf-8")
        except (OSError, ValueError) as e:
            self.fenster.zeige_fehler(f"Konnte nicht gelöscht werden:\n{e}")
            return
        self.laden()
        self.fenster.status.configure(text="Textfeld-Regel gelöscht.")

    def _datei_oeffnen(self):
        try:
            os.startfile(str(self._datei()))
        except OSError:
            pass
