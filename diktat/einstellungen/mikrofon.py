"""Reiter „Mikrofon“: Auswahl, Pegeltest, Mikrofon offen halten."""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .. import geraete
from . import stil
from .fenster import KonfigReiter

STANDARD = "Windows-Standard"
TEST_S = 5


def pegel_bewertung(spitze: float) -> str:
    """Ergebnis des Pegeltests in Alltagssprache (Schwellen wie bei „Aufnahme stumm“ im Tool)."""
    if spitze < 0.01:
        return "stumm – ist das Mikrofon stummgeschaltet oder das Headset aus?"
    if spitze < 0.05:
        return "leise – näher ans Mikrofon oder in Windows lauter stellen"
    return "gut – das Mikrofon hört dich"


class Mikrofon(KonfigReiter):
    titel = "Mikrofon"
    felder = ("mikrofon", "mikrofon_offen_halten")

    def __init__(self, eltern, fenster):
        super().__init__(eltern, fenster)
        self._namen: list[str] = []
        self.ueberschrift("Mikrofon")
        self.feld("mikrofon", steuer=self._auswahl)
        self.var["mikrofon"].trace_add("write", lambda *a: self._box_zeigen())

        self.ueberschrift("Pegeltest", f"Prüft {TEST_S} Sekunden lang, ob das gewählte Mikrofon dich hört. Einfach "
                                       "normal sprechen.")
        z = ttk.Frame(self.innen)
        z.grid(row=self._zeile, column=0, sticky="we", pady=(4, 0))
        self._zeile += 1
        self._test_knopf = ttk.Button(z, text="Testen", command=self._testen)
        self._test_knopf.grid(row=0, column=0, sticky="w")
        self.pegel = ttk.Progressbar(z, length=stil.px(360), maximum=1.0)
        self.pegel.grid(row=0, column=1, padx=(12, 0))
        self._ergebnis = ttk.Label(z, style="Titel.TLabel")
        self._ergebnis.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._werte: queue.Queue = queue.Queue()

        self.ueberschrift("Für Funkheadsets")
        self.feld("mikrofon_offen_halten")
        self._liste_laden()

    def _auswahl(self, eltern):
        f = ttk.Frame(eltern)
        self.box = ttk.Combobox(f, state="readonly", width=44)
        self.box.pack(side="left")
        self.box.bind("<<ComboboxSelected>>", self._gewaehlt)
        ttk.Button(f, text="Liste aktualisieren", command=self._liste_laden).pack(side="left", padx=(8, 0))
        return f

    def _liste_laden(self):
        self._namen = geraete.mikrofone()
        self._box_zeigen()

    def _box_zeigen(self):
        aktuell = self.var["mikrofon"].get()
        namen = list(self._namen)
        if aktuell and aktuell not in namen:
            namen.append(aktuell)
        anzeigen = [STANDARD] + [n + ("  (nicht angeschlossen)" if n not in self._namen else "") for n in namen]
        self._box_namen = [""] + namen
        self.box.configure(values=anzeigen)
        if aktuell in self._box_namen:
            self.box.current(self._box_namen.index(aktuell))

    def _gewaehlt(self, _e=None):
        i = self.box.current()
        if i >= 0:
            self.var["mikrofon"].set(self._box_namen[i])

    # --- Pegeltest ------------------------------------------------------------------------------------------------
    def _testen(self):
        self._test_knopf.state(["disabled"])
        self._ergebnis.configure(text="Bitte sprechen …")
        name = self.var["mikrofon"].get()
        threading.Thread(target=self._messen, args=(name,), daemon=True).start()
        self.after(50, self._anzeigen)

    def _messen(self, name: str):
        spitze = 0.0
        try:
            import sounddevice as sd
            nummer = geraete.mikrofon_nummer(name) if name else None
            with sd.InputStream(device=nummer, samplerate=16000, channels=1, dtype="float32") as s:
                ende = time.monotonic() + TEST_S
                while time.monotonic() < ende:
                    daten, _ = s.read(1600)
                    p = float(abs(daten).max()) if len(daten) else 0.0
                    spitze = max(spitze, p)
                    self._werte.put(("pegel", p))
            self._werte.put(("fertig", spitze))
        except Exception as e:  # noqa: BLE001
            self._werte.put(("fehler", str(e)))

    def _anzeigen(self):
        try:
            while True:
                art, wert = self._werte.get_nowait()
                if art == "pegel":
                    self.pegel["value"] = min(1.0, wert * 3)  # leise Stimmen sichtbar machen
                    continue
                self._test_knopf.state(["!disabled"])
                self.pegel["value"] = 0
                self._ergebnis.configure(text=("Ergebnis: " + pegel_bewertung(wert)) if art == "fertig"
                                         else f"Mikrofon ließ sich nicht öffnen: {wert}")
                return
        except queue.Empty:
            pass
        try:
            self.after(50, self._anzeigen)
        except tk.TclError:
            pass
