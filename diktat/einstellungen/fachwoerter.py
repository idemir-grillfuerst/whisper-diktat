"""Reiter „Fachwörter“: Begriffe, die Whisper richtig schreiben soll."""
import tkinter as tk
from tkinter import ttk

from . import stil
from .daten import FACHWORT_GRENZE, fachwort_laenge
from .fenster import Reiter


class Fachwoerter(Reiter):
    titel = "Fachwörter"

    def __init__(self, eltern, fenster):
        super().__init__(eltern, fenster)
        self._original = ""
        f = ttk.Frame(self, padding=(stil.px(22), stil.px(16)))
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)
        ttk.Label(f, text="Fachwörter", style="Ueberschrift.TLabel").grid(row=0, column=0, sticky="w")
        stil.erklaerung(f, "Namen und Begriffe, die Whisper sonst falsch schreibt (Personen, Firmen, Produkte). Ein "
                        "Begriff pro Zeile, # am Zeilenanfang = Notiz. Whisper liest nur die ersten "
                        f"{FACHWORT_GRENZE} Zeichen – Wichtiges nach oben, nicht zu viel: Eine sehr lange Liste "
                        "kann Whisper verwirren. Gilt ab dem nächsten Diktat.").grid(row=1, column=0, sticky="w",
                                                                                   pady=(2, 10))
        rahmen = ttk.Frame(f)
        rahmen.grid(row=2, column=0, sticky="nsew")
        rahmen.columnconfigure(0, weight=1)
        rahmen.rowconfigure(0, weight=1)
        self.text = tk.Text(rahmen, wrap="none", undo=True, font=("Segoe UI", 10), relief="flat",
                            padx=stil.px(8), pady=stil.px(6))
        balken = ttk.Scrollbar(rahmen, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=balken.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        balken.grid(row=0, column=1, sticky="ns")
        self.zaehler = ttk.Label(f, style="Erklaerung.TLabel")
        self.zaehler.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.text.bind("<<Modified>>", self._geaendert)
        self.text.bind("<KeyRelease>", self._geaendert)
        self.after_idle(self._farben)

    def _farben(self):
        try:
            s = ttk.Style(self)
            hg = s.lookup("TEntry", "fieldbackground") or s.lookup("TFrame", "background")
            vg = s.lookup("TLabel", "foreground")
            if hg:
                self.text.configure(background=hg, insertbackground=vg or "black")
            if vg:
                self.text.configure(foreground=vg)
        except tk.TclError:
            pass

    def _inhalt(self) -> str:
        return self.text.get("1.0", "end-1c")

    def laden(self):
        d = self.fenster.dateien["fachwoerter"]
        self._original = d.read_text(encoding="utf-8") if d.exists() else ""
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self._original.rstrip("\n"))
        self.text.edit_modified(False)
        self.text.edit_reset()
        self._geaendert()

    def _geaendert(self, _e=None):
        self.text.edit_modified(False)
        laenge = fachwort_laenge(self._inhalt())
        zuviel = laenge > FACHWORT_GRENZE
        self.zaehler.configure(text=f"{laenge} / {FACHWORT_GRENZE} Zeichen"
                               + (" – zu viel, Whisper liest nur den Anfang" if zuviel else ""),
                               style="Fehler.TLabel" if zuviel else "Erklaerung.TLabel")
        self.melden()

    def geaendert(self) -> bool:
        return self._inhalt().rstrip("\n") != self._original.rstrip("\n")

    def uebernehmen(self) -> list[str]:
        neu = self._inhalt().rstrip("\n") + "\n"
        self.fenster.dateien["fachwoerter"].write_text(neu, encoding="utf-8")
        self._original = neu
        self.melden()
        return []
