"""Reiter „Info“: Version, Pfade, Anleitung, Log, Ordner, Dateien von Hand bearbeiten."""
import os
import subprocess
import sys
from tkinter import ttk

from .. import PROJEKT, __author__
from . import stil
from .fenster import Reiter

LOG_DATEI = PROJEKT / "logs" / "diktat.log"
ANLEITUNG = PROJEKT / "docs" / "SPRACHBEFEHLE.md"


def version() -> str:
    try:
        r = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=PROJEKT, capture_output=True,
                           text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        return r.stdout.strip() or "unbekannt"
    except (OSError, subprocess.SubprocessError):
        return "unbekannt"


def _oeffne(pfad) -> None:
    try:
        os.startfile(str(pfad))
    except OSError:
        pass


class Info(Reiter):
    titel = "Info"

    def __init__(self, eltern, fenster):
        super().__init__(eltern, fenster)
        f = ttk.Frame(self, padding=(20, 16))
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="whisper-diktat", style="Ueberschrift.TLabel").pack(anchor="w")
        ttk.Label(f, text=f"von {__author__} · entwickelt mit Unterstützung von Claude (Anthropic)",
                  style="Titel.TLabel").pack(anchor="w", pady=(2, 0))
        stil.erklaerung(f, "Lokales Diktier-Tool: nimmt per Tastenkombination auf, schreibt mit Whisper auf deinem "
                        "Rechner mit und fügt den Text dort ein, wo der Cursor steht. Die Aufnahme verlässt den "
                        "Rechner nie.").pack(anchor="w", pady=(2, 12))
        self._version = ttk.Label(f, text="Version: …")
        self._version.pack(anchor="w")
        ttk.Label(f, text=f"Projektordner: {PROJEKT}").pack(anchor="w")
        ttk.Label(f, text=f"Python: {sys.executable}").pack(anchor="w")

        ttk.Label(f, text="Hilfe und Fehlersuche", style="Titel.TLabel").pack(anchor="w", pady=(20, 6))
        for text, ziel in (("Anleitung: Sprachbefehle", ANLEITUNG), ("Log öffnen", LOG_DATEI),
                           ("Projektordner öffnen", PROJEKT)):
            ttk.Button(f, text=text, command=lambda z=ziel: _oeffne(z), width=32).pack(anchor="w", pady=2)

        ttk.Label(f, text="Für Fortgeschrittene", style="Titel.TLabel").pack(anchor="w", pady=(20, 6))
        stil.erklaerung(f, "Alle Einstellungen stehen in Textdateien im Projektordner. Dieses Fenster schreibt "
                        "nur die geänderten Werte und lässt deine Kommentare stehen. Nach Änderungen von Hand: "
                        "Fenster schließen und neu öffnen.").pack(anchor="w", pady=(0, 6))
        ttk.Button(f, text="Dateien von Hand bearbeiten …", command=self._dateien, width=32).pack(anchor="w")

    def laden(self):
        self._version.configure(text=f"Version: {version()}")

    def _dateien(self):
        for d in self.fenster.dateien.values():
            if d.exists():
                subprocess.Popen(["notepad.exe", str(d)])
